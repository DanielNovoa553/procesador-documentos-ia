from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import servicio
from app.api import app
from app.db import Base, get_db
from app.extractor import ExtraccionError
from app.schemas import nueva_factura, nuevo_concepto

PDF = b"%PDF-1.4\ncontenido de prueba"


def factura(**cambios):
    datos = dict(
        emisor="Comercial Norte S.A. de C.V.",
        rfc_emisor="CNO010203AB1",
        fecha=(date.today() - timedelta(days=5)).isoformat(),
        subtotal=1000.0,
        iva=160.0,
        total=1160.0,
        conceptos=[nuevo_concepto(descripcion="Licencia", cantidad=1, importe=1000.0)],
    )
    datos.update(cambios)
    return nueva_factura(**datos)


@pytest.fixture
def client(monkeypatch):
    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=motor)
    Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)

    def reemplazo():
        db = Sesion()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = reemplazo
    monkeypatch.setattr(servicio, "extraer_segun_modo", lambda nombre, contenido: factura())
    yield TestClient(app)
    app.dependency_overrides.clear()


def subir(client, contenido=PDF, nombre="factura.pdf"):
    return client.post("/documentos", files={"archivo": (nombre, contenido, "application/pdf")})


def test_subir_factura_correcta(client):
    r = subir(client)
    assert r.status_code == 201
    assert r.json()["estado"] == "validado"
    assert r.json()["motivos"] == []


def test_factura_con_total_incorrecto_va_a_revision(client, monkeypatch):
    monkeypatch.setattr(servicio, "extraer_segun_modo", lambda n, c: factura(total=9999.0))
    r = subir(client, PDF + b"2")
    assert r.status_code == 201
    assert r.json()["estado"] == "revision_manual"
    assert r.json()["motivos"][0]["codigo"] == "total_no_coincide"


def test_documento_repetido_devuelve_el_guardado(client):
    primero = subir(client)
    segundo = subir(client)
    assert primero.status_code == 201
    assert segundo.status_code == 200
    assert segundo.json()["id"] == primero.json()["id"]


def test_rechaza_archivo_que_no_es_pdf(client):
    assert subir(client, b"hola mundo").status_code == 400


def test_error_de_extraccion_devuelve_502(client, monkeypatch):
    def falla(nombre, contenido):
        raise ExtraccionError("fallo simulado")

    monkeypatch.setattr(servicio, "extraer_segun_modo", falla)
    r = subir(client, PDF + b"3")
    assert r.status_code == 502


def test_listar_y_filtrar_por_estado(client, monkeypatch):
    subir(client)
    monkeypatch.setattr(servicio, "extraer_segun_modo", lambda n, c: factura(total=9999.0))
    subir(client, PDF + b"2")

    assert len(client.get("/documentos").json()) == 2
    assert len(client.get("/documentos?estado=validado").json()) == 1
    assert len(client.get("/documentos?estado=revision_manual").json()) == 1
    assert client.get("/documentos?estado=otro").status_code == 422


def test_detalle_y_documento_inexistente(client):
    creado = subir(client).json()
    assert client.get(f"/documentos/{creado['id']}").status_code == 200
    assert client.get("/documentos/9999").status_code == 404


def test_eliminar_documento(client):
    creado = subir(client).json()
    assert client.delete(f"/documentos/{creado['id']}").status_code == 204
    assert client.get(f"/documentos/{creado['id']}").status_code == 404
    assert client.delete("/documentos/9999").status_code == 404