import json
from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import ConceptoDocumento, Documento
from app.persistencia import migrar_documentos
from app.schemas import nueva_factura, nuevo_concepto


def test_migrar_documentos_existentes_crea_columnas_y_conceptos():
    motor = create_engine("sqlite://")
    factura = nueva_factura(
        emisor="Distribuidora Aurora",
        rfc_emisor="DAU010203AB1",
        fecha=(date.today() - timedelta(days=1)).isoformat(),
        subtotal=1000.0,
        iva=160.0,
        total=1160.0,
        folio="F-12",
        folio_fiscal="41F38E36-A5CB-4A0E-AEAC-D944605CCAF5",
        conceptos=[
            nuevo_concepto(
                descripcion="Servicio anual",
                cantidad=1,
                importe=1000.0,
            )
        ],
    )
    with motor.begin() as conexion:
        conexion.execute(text(
            "CREATE TABLE documentos ("
            "id INTEGER PRIMARY KEY, archivo VARCHAR(255) NOT NULL, "
            "sha256 VARCHAR(64) NOT NULL, estado VARCHAR(20) NOT NULL, "
            "motivos JSON NOT NULL, datos JSON NOT NULL, modelo VARCHAR(100) NOT NULL, "
            "creado_en DATETIME NOT NULL)"
        ))
        conexion.execute(
            text(
                "INSERT INTO documentos "
                "(id, archivo, sha256, estado, motivos, datos, modelo, creado_en) "
                "VALUES (1, 'factura.pdf', 'hash', 'validado', '[]', :datos, 'mock', "
                "'2026-10-31 00:00:00')"
            ),
            {"datos": json.dumps(factura.model_dump())},
        )

    migrar_documentos(motor)
    migrar_documentos(motor)

    with Session(motor) as db:
        documento = db.get(Documento, 1)
        assert documento.emisor == "Distribuidora Aurora"
        assert documento.rfc_emisor == "DAU010203AB1"
        assert documento.total == 1160.0
        assert documento.folio == "F-12"
        assert len(documento.conceptos) == 1
        concepto = db.query(ConceptoDocumento).one()
        assert concepto.posicion == 0
        assert concepto.descripcion == "Servicio anual"
    motor.dispose()
