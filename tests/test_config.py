import pytest
from fastapi.testclient import TestClient

from app import configuracion
from app.api import app


@pytest.fixture
def client(monkeypatch):
    for var, valor in (
        ("LLM_PROVEEDOR", "ollama"),
        ("OLLAMA_MODEL", "llama3.1:8b"),
        ("GEMINI_MODEL", "gemini-3.8-flash"),
        ("GEMINI_ENTRADA", "mascara"),
        ("GEMINI_API_KEY", "clave-de-prueba"),
    ):
        monkeypatch.setenv(var, valor)
    monkeypatch.setattr(configuracion, "ollama_modelos", lambda: ["llama3.1:8b", "llama3.2:3b"])
    return TestClient(app)


def guardar(client, **datos):
    base = {"proveedor": "gemini", "modelo": "gemini-3.8-flash", "privacidad": "mascara", "acepta_riesgo": False}
    return client.put("/config", json={**base, **datos})


def test_lee_la_configuracion_y_los_modelos(client):
    datos = client.get("/config").json()
    assert datos["proveedor"] == "ollama" and datos["modelo"] == "llama3.1:8b"
    assert datos["ollama_modelos"] == ["llama3.1:8b", "llama3.2:3b"]
    assert "gemini-3.8-flash" in datos["gemini_modelos"]
    assert "clave-de-prueba" not in str(datos)


def test_cambia_a_ollama_con_otro_modelo(client):
    r = client.put("/config", json={"proveedor": "ollama", "modelo": "llama3.2:3b"})
    assert r.status_code == 200 and r.json()["modelo"] == "llama3.2:3b"
    assert configuracion.estado()["proveedor"] == "ollama"


def test_modelo_de_ollama_no_instalado_se_rechaza(client):
    assert client.put("/config", json={"proveedor": "ollama", "modelo": "otro:1b"}).status_code == 400


def test_gemini_con_mascara_configura_el_entorno(client):
    r = guardar(client)
    assert r.status_code == 200
    estado = r.json()
    assert estado["proveedor"] == "gemini" and estado["privacidad"] == "mascara"


def test_gemini_sin_mascara_exige_aceptar_el_riesgo(client):
    assert guardar(client, privacidad="sin_mascara").status_code == 400
    assert configuracion.estado()["proveedor"] == "ollama"

    r = guardar(client, privacidad="sin_mascara", acepta_riesgo=True)
    assert r.status_code == 200 and r.json()["privacidad"] == "sin_mascara"


def test_gemini_sin_clave_se_rechaza(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert guardar(client).status_code == 400


def test_modelo_de_gemini_desconocido_se_rechaza(client):
    assert guardar(client, modelo="no-existe").status_code == 400
