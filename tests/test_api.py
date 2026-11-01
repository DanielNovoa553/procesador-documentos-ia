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


def test_aprobar_documento_registra_bitacora(client):
    documento = subir(client).json()

    r = client.post(
        f"/documentos/{documento['id']}/aprobar",
        json={"revisor": "Ana", "comentario": "Verificado contra el PDF"},
    )

    assert r.status_code == 200
    assert r.json()["estado"] == "aprobado"
    bitacora = client.get(f"/documentos/{documento['id']}/bitacora").json()
    assert len(bitacora) == 1
    assert bitacora[0]["accion"] == "aprobar"
    assert bitacora[0]["revisor"] == "Ana"
    assert bitacora[0]["comentario"] == "Verificado contra el PDF"
    assert bitacora[0]["estado_anterior"] == "validado"
    assert bitacora[0]["estado_nuevo"] == "aprobado"
    assert bitacora[0]["datos_anteriores"] == bitacora[0]["datos_nuevos"]


def test_corregir_documento_actualiza_datos_y_motivos(client, monkeypatch):
    monkeypatch.setattr(servicio, "extraer_segun_modo", lambda n, c: factura(total=9999.0))
    documento = subir(client, PDF + b"corregir").json()
    datos_corregidos = factura().model_dump()

    r = client.put(
        f"/documentos/{documento['id']}/corregir",
        json={
            "revisor": "Luis",
            "comentario": "Se corrigió el total",
            "datos": datos_corregidos,
        },
    )

    assert r.status_code == 200
    assert r.json()["estado"] == "corregido"
    assert r.json()["datos"]["total"] == 1160.0
    assert r.json()["motivos"] == []
    bitacora = client.get(f"/documentos/{documento['id']}/bitacora").json()[0]
    assert bitacora["accion"] == "corregir"
    assert bitacora["estado_anterior"] == "revision_manual"
    assert bitacora["datos_anteriores"]["total"] == 9999.0
    assert bitacora["datos_nuevos"]["total"] == 1160.0


def test_correccion_invalida_sigue_en_revision_y_rechazo_exige_motivo(client):
    documento = subir(client).json()
    datos_corregidos = factura(total=9999.0).model_dump()
    corregido = client.put(
        f"/documentos/{documento['id']}/corregir",
        json={"datos": datos_corregidos},
    )

    assert corregido.status_code == 200
    assert corregido.json()["estado"] == "revision_manual"
    assert corregido.json()["motivos"][0]["codigo"] == "total_no_coincide"
    assert client.post(f"/documentos/{documento['id']}/rechazar", json={}).status_code == 422


def test_rechazar_documento_registra_motivo(client):
    documento = subir(client).json()
    r = client.post(
        f"/documentos/{documento['id']}/rechazar",
        json={"revisor": "Ana", "motivo": "El emisor no corresponde"},
    )

    assert r.status_code == 200
    assert r.json()["estado"] == "rechazado"
    cambio = client.get(f"/documentos/{documento['id']}/bitacora").json()[0]
    assert cambio["accion"] == "rechazar"
    assert cambio["comentario"] == "El emisor no corresponde"


def test_filtro_acepta_estados_de_revision(client):
    documento = subir(client).json()
    client.post(f"/documentos/{documento['id']}/aprobar", json={})

    assert len(client.get("/documentos?estado=aprobado").json()) == 1
    assert client.get("/documentos?estado=corregido").json() == []
    assert client.get("/documentos?estado=revision_desconocida").status_code == 422


def test_revalidar_tambien_registra_cambio_en_bitacora(client):
    documento = subir(client).json()
    client.post(f"/documentos/{documento['id']}/aprobar", json={})

    r = client.post(f"/documentos/{documento['id']}/revalidar")

    assert r.status_code == 200
    assert r.json()["estado"] == "validado"
    bitacora = client.get(f"/documentos/{documento['id']}/bitacora").json()
    assert [cambio["accion"] for cambio in bitacora] == ["revalidar", "aprobar"]
    assert bitacora[0]["estado_anterior"] == "aprobado"


def test_corregir_rechaza_datos_que_no_cumplen_el_esquema(client):
    documento = subir(client).json()
    r = client.put(
        f"/documentos/{documento['id']}/corregir",
        json={"datos": {"emisor": "Sin conceptos"}},
    )

    assert r.status_code == 422
    assert client.get(f"/documentos/{documento['id']}").json()["estado"] == "validado"


def test_bitacora_de_documento_inexistente(client):
    assert client.get("/documentos/9999/bitacora").status_code == 404