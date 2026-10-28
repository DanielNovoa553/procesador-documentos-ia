import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import servicio
from app.db import Base, engine, get_db
from app.extractor import ExtraccionError
from app.models import Documento
from app.validators import validar

MAX_BYTES = 5 * 1024 * 1024
ESTADOS = {"validado", "revision_manual"}
RAIZ = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(RAIZ / "static" / "index.html")


@app.get("/info")
def info():
    return {"modo": servicio.modo(), "modelo": servicio.modelo()}


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
        datos=factura.model_dump(),
        modelo=servicio.etiqueta_modelo(),
    )
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
    limite: int = Query(default=50, ge=1, le=200),
    desplazamiento: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if estado is not None and estado not in ESTADOS:
        raise HTTPException(status_code=422, detail="Estado inválido: usa validado o revision_manual")
    consulta = select(Documento)
    if estado:
        consulta = consulta.where(Documento.estado == estado)
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
    db.delete(documento)
    db.commit()
    return Response(status_code=204)