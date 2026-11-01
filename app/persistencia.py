import json

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import ConceptoDocumento, Documento
from app.schemas import Factura, factura_desde_json

COLUMNAS_BUSQUEDA = {
    "emisor": "VARCHAR(255)",
    "rfc_emisor": "VARCHAR(20)",
    "nombre_receptor": "VARCHAR(255)",
    "rfc_receptor": "VARCHAR(20)",
    "fecha": "VARCHAR(32)",
    "total": "FLOAT",
    "folio": "VARCHAR(100)",
    "folio_fiscal": "VARCHAR(64)",
}


def actualizar_documento_desde_factura(documento: Documento, factura: Factura) -> None:
    datos = factura.model_dump()
    documento.datos = datos
    for campo in COLUMNAS_BUSQUEDA:
        setattr(documento, campo, datos[campo])
    documento.conceptos = [
        ConceptoDocumento(posicion=posicion, **concepto.model_dump())
        for posicion, concepto in enumerate(factura.conceptos)
    ]


def migrar_documentos(engine: Engine) -> None:
    inspector = inspect(engine)
    columnas = {columna["name"] for columna in inspector.get_columns("documentos")}
    faltantes = {
        nombre: tipo for nombre, tipo in COLUMNAS_BUSQUEDA.items()
        if nombre not in columnas
    }

    if faltantes:
        with engine.begin() as conexion:
            for nombre, tipo in faltantes.items():
                conexion.execute(text(f"ALTER TABLE documentos ADD COLUMN {nombre} {tipo}"))

    ConceptoDocumento.__table__.create(bind=engine, checkfirst=True)
    for indice in Documento.__table__.indexes:
        indice.create(bind=engine, checkfirst=True)
    for indice in ConceptoDocumento.__table__.indexes:
        indice.create(bind=engine, checkfirst=True)

    with Session(engine) as db:
        documentos = db.scalars(select(Documento)).all()
        for documento in documentos:
            factura = factura_desde_json(json.dumps(documento.datos))
            if _necesita_sincronizacion(documento, factura):
                actualizar_documento_desde_factura(documento, factura)
        db.commit()


def _necesita_sincronizacion(documento: Documento, factura: Factura) -> bool:
    datos = factura.model_dump()
    if any(getattr(documento, campo) != datos[campo] for campo in COLUMNAS_BUSQUEDA):
        return True

    if len(documento.conceptos) != len(factura.conceptos):
        return True
    return any(
        concepto.posicion != posicion
        or any(
            getattr(concepto, campo) != valor
            for campo, valor in datos_concepto.model_dump().items()
        )
        for posicion, (concepto, datos_concepto) in enumerate(
            zip(documento.conceptos, factura.conceptos)
        )
    )
