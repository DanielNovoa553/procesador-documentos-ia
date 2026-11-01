import hashlib
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import os
from app.schemas import factura_desde_json
from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import String, cast, delete, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app import configuracion, servicio
from app.db import Base, SessionLocal, engine, get_db
from app.extractor import ExtraccionError
from app.models import BitacoraRevision, ConfiguracionPersistida, ConceptoDocumento, Documento
from app.persistencia import actualizar_documento_desde_factura, migrar_documentos
from app.validators import validar

MAX_BYTES = 5 * 1024 * 1024
ESTADOS = {"validado", "revision_manual", "aprobado", "corregido", "rechazado"}
RAIZ = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrar_documentos(engine)
    with SessionLocal() as db:
        restaurar_configuracion(db)
    yield


app = FastAPI(title="Procesador inteligente de documentos", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=RAIZ / "static"), name="static")


class MotivoOut(BaseModel):
    codigo: str
    detalle: str


class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    archivo: str
    estado: str
    motivos: list[MotivoOut]
    datos: dict
    modelo: str
    creado_en: datetime


class RevisionIn(BaseModel):
    revisor: str = Field(default="Revisor", min_length=1, max_length=100)
    comentario: str | None = Field(default=None, max_length=1000)


class CorreccionIn(RevisionIn):
    datos: dict


class RechazoIn(BaseModel):
    revisor: str = Field(default="Revisor", min_length=1, max_length=100)
    motivo: str = Field(min_length=1, max_length=1000)

    @field_validator("motivo")
    @classmethod
    def motivo_no_vacio(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("El motivo del rechazo no puede estar vacío")
        return valor.strip()


class BitacoraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    documento_id: int
    accion: str
    revisor: str
    comentario: str | None
    estado_anterior: str
    estado_nuevo: str
    datos_anteriores: dict
    datos_nuevos: dict
    motivos_anteriores: list[MotivoOut]
    motivos_nuevos: list[MotivoOut]
    creado_en: datetime


def _registrar_revision(
    db: Session,
    documento: Documento,
    accion: str,
    revisor: str,
    comentario: str | None,
    estado_anterior: str,
    datos_anteriores: dict,
    motivos_anteriores: list,
):
    db.add(
        BitacoraRevision(
            documento_id=documento.id,
            accion=accion,
            revisor=revisor.strip() or "Revisor",
            comentario=comentario.strip() if comentario and comentario.strip() else None,
            estado_anterior=estado_anterior,
            estado_nuevo=documento.estado,
            datos_anteriores=datos_anteriores,
            datos_nuevos=deepcopy(documento.datos),
            motivos_anteriores=motivos_anteriores,
            motivos_nuevos=deepcopy(documento.motivos),
        )
    )


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(RAIZ / "static" / "index.html")


@app.get("/info")
def info():
    return {"modo": servicio.modo(), "modelo": servicio.modelo_activo()}


class ConfigIn(BaseModel):
    proveedor: str
    modelo: str
    privacidad: str = "mascara"
    acepta_riesgo: bool = False


def restaurar_configuracion(db: Session) -> None:
    guardada = db.get(ConfiguracionPersistida, 1)
    if guardada is not None:
        configuracion.restaurar(
            guardada.proveedor, guardada.modelo, guardada.privacidad
        )


@app.get("/config")
def leer_config(db: Session = Depends(get_db)):
    restaurar_configuracion(db)
    return {"modo": servicio.modo(), **configuracion.estado()}


@app.put("/config")
def guardar_config(datos: ConfigIn, db: Session = Depends(get_db)):
    variables = ("LLM_PROVEEDOR", "OLLAMA_MODEL", "GEMINI_MODEL", "GEMINI_ENTRADA")
    anterior = {nombre: os.getenv(nombre) for nombre in variables}
    try:
        actual = configuracion.aplicar(
            datos.proveedor, datos.modelo, datos.privacidad, datos.acepta_riesgo
        )
    except configuracion.ConfiguracionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        guardada = db.get(ConfiguracionPersistida, 1)
        if guardada is None:
            guardada = ConfiguracionPersistida(
                id=1,
                proveedor=datos.proveedor.strip().lower(),
                modelo=datos.modelo.strip(),
                privacidad=datos.privacidad,
            )
            db.add(guardada)
        else:
            guardada.proveedor = datos.proveedor.strip().lower()
            guardada.modelo = datos.modelo.strip()
            guardada.privacidad = datos.privacidad
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        for nombre, valor in anterior.items():
            if valor is None:
                os.environ.pop(nombre, None)
            else:
                os.environ[nombre] = valor
        raise HTTPException(status_code=500, detail="No se pudo guardar la configuración") from e
    return {"modo": servicio.modo(), **actual}


@app.post("/documentos", response_model=DocumentoOut, status_code=201)
def subir_documento(
    response: Response,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    contenido = archivo.file.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 5 MB")
    if not contenido.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="El archivo no es un PDF válido")

    huella = hashlib.sha256(contenido).hexdigest()
    existente = db.scalar(select(Documento).where(Documento.sha256 == huella))
    if existente:
        response.status_code = 200
        return existente

    nombre = Path(archivo.filename or "documento.pdf").name[:255]
    try:
        factura = servicio.extraer_segun_modo(nombre, contenido)
    except ExtraccionError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo extraer el documento: {e}")

    resultado = validar(factura)
    documento = Documento(
        archivo=nombre,
        sha256=huella,
        estado=resultado.estado,
        motivos=[{"codigo": m.codigo, "detalle": m.detalle} for m in resultado.motivos],
        modelo=servicio.etiqueta_modelo(),
    )
    actualizar_documento_desde_factura(documento, factura)
    db.add(documento)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existente = db.scalar(select(Documento).where(Documento.sha256 == huella))
        response.status_code = 200
        return existente
    return documento


@app.get("/documentos", response_model=list[DocumentoOut])
def listar_documentos(
    estado: str | None = Query(default=None),
    busqueda: str | None = Query(default=None, max_length=200),
    limite: int = Query(default=50, ge=1, le=200),
    desplazamiento: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS:
        raise HTTPException(status_code=422, detail="Estado inválido")
    consulta = select(Documento)
    if estado:
        consulta = consulta.where(Documento.estado == estado)
    termino = (busqueda or "").strip()
    if termino:
        patron = f"%{termino}%"
        consulta = consulta.where(
            or_(
                Documento.archivo.ilike(patron),
                Documento.emisor.ilike(patron),
                Documento.rfc_emisor.ilike(patron),
                Documento.nombre_receptor.ilike(patron),
                Documento.rfc_receptor.ilike(patron),
                Documento.folio.ilike(patron),
                Documento.folio_fiscal.ilike(patron),
                Documento.fecha.ilike(patron),
                cast(Documento.total, String).ilike(patron),
                Documento.conceptos.any(ConceptoDocumento.descripcion.ilike(patron)),
            )
        )
    consulta = consulta.order_by(Documento.id.desc()).limit(limite).offset(desplazamiento)
    return db.scalars(consulta).all()


@app.get("/documentos/{documento_id}", response_model=DocumentoOut)
def obtener_documento(documento_id: int, db: Session = Depends(get_db)):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return documento

@app.delete("/documentos/{documento_id}", status_code=204)
def eliminar_documento(documento_id: int, db: Session = Depends(get_db)):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    db.execute(delete(BitacoraRevision).where(BitacoraRevision.documento_id == documento_id))
    db.delete(documento)
    db.commit()
    return Response(status_code=204)


@app.post("/documentos/{documento_id}/aprobar", response_model=DocumentoOut)
def aprobar_documento(
    documento_id: int, datos: RevisionIn, db: Session = Depends(get_db)
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    anteriores = (
        documento.estado,
        deepcopy(documento.datos),
        deepcopy(documento.motivos),
    )
    documento.estado = "aprobado"
    _registrar_revision(
        db, documento, "aprobar", datos.revisor, datos.comentario, *anteriores
    )
    db.commit()
    return documento


@app.put("/documentos/{documento_id}/corregir", response_model=DocumentoOut)
def corregir_documento(
    documento_id: int, datos: CorreccionIn, db: Session = Depends(get_db)
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    try:
        factura = factura_desde_json(json.dumps(datos.datos))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_context=False))

    anteriores = (
        documento.estado,
        deepcopy(documento.datos),
        deepcopy(documento.motivos),
    )
    resultado = validar(factura)
    actualizar_documento_desde_factura(documento, factura)
    documento.estado = "corregido" if resultado.estado == "validado" else "revision_manual"
    documento.motivos = [
        {"codigo": motivo.codigo, "detalle": motivo.detalle}
        for motivo in resultado.motivos
    ]
    _registrar_revision(
        db, documento, "corregir", datos.revisor, datos.comentario, *anteriores
    )
    db.commit()
    return documento


@app.post("/documentos/{documento_id}/rechazar", response_model=DocumentoOut)
def rechazar_documento(
    documento_id: int, datos: RechazoIn, db: Session = Depends(get_db)
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    anteriores = (
        documento.estado,
        deepcopy(documento.datos),
        deepcopy(documento.motivos),
    )
    documento.estado = "rechazado"
    _registrar_revision(
        db, documento, "rechazar", datos.revisor, datos.motivo, *anteriores
    )
    db.commit()
    return documento


@app.get("/documentos/{documento_id}/bitacora", response_model=list[BitacoraOut])
def consultar_bitacora(documento_id: int, db: Session = Depends(get_db)):
    if db.get(Documento, documento_id) is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    consulta = (
        select(BitacoraRevision)
        .where(BitacoraRevision.documento_id == documento_id)
        .order_by(BitacoraRevision.id.desc())
    )
    return db.scalars(consulta).all()


@app.post("/documentos/{documento_id}/revalidar", response_model=DocumentoOut)
def revalidar_documento(documento_id: int, db: Session = Depends(get_db)):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    anteriores = (
        documento.estado,
        deepcopy(documento.datos),
        deepcopy(documento.motivos),
    )
    resultado = validar(factura_desde_json(json.dumps(documento.datos)))
    documento.estado = resultado.estado
    documento.motivos = [{"codigo": m.codigo, "detalle": m.detalle} for m in resultado.motivos]
    _registrar_revision(
        db, documento, "revalidar", "Sistema", None, *anteriores
    )
    db.commit()
    return documento