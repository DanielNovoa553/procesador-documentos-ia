from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import configuracion
from app.api import app
from app.db import Base, get_db


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
    monkeypatch.setattr(
        configuracion,
        "_listar_modelos_gemini_api",
        lambda api_key: [
            "gemini-3.8-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-exp",
            "gemini-3.1-flash",
            "gemini-3.0-pro",
        ],
    )
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
    yield TestClient(app)
    app.dependency_overrides.clear()
    motor.dispose()


def guardar(client, **datos):
    base = {"proveedor": "gemini", "modelo": "gemini-3.8-flash", "privacidad": "mascara", "acepta_riesgo": False}
    return client.put("/config", json={**base, **datos})


def test_lee_la_configuracion_y_los_modelos(client):
    datos = client.get("/config").json()
    assert datos["proveedor"] == "ollama" and datos["modelo"] == "llama3.1:8b"
    assert datos["ollama_modelos"] == ["llama3.1:8b", "llama3.2:3b"]
    assert "gemini-3.8-flash" in datos["gemini_modelos"]
    assert "clave-de-prueba" not in str(datos)


def test_muestra_hasta_diez_modelos_disponibles_en_gemini(client):
    datos = client.get("/config").json()

    assert len(datos["gemini_modelos"]) == 10
    assert datos["gemini_modelos_fuente"] == "api"
    assert "gemini-3.8-flash" in datos["gemini_modelos"]
    assert "gemini-3.0-pro" not in datos["gemini_modelos"]


def test_lista_solo_modelos_gemini_compatibles_con_generate_content(monkeypatch):
    elementos = [
        SimpleNamespace(name="models/gemini-2.5-flash", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/gemini-embedding", supported_actions=["embedContent"]),
        SimpleNamespace(name="models/otro-modelo", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/gemini-2.5-flash", supported_actions=["generateContent"]),
    ]

    class Modelos:
        def list(self):
            return elementos

    class Cliente:
        models = Modelos()

    monkeypatch.setattr(configuracion.genai, "Client", lambda **kwargs: Cliente())

    assert configuracion._listar_modelos_gemini_api("clave") == ["gemini-2.5-flash"]


def test_modelo_actual_tiene_prioridad_dentro_del_limite(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "clave-prioridad")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-modelo-actual")
    monkeypatch.setattr(
        configuracion,
        "_listar_modelos_gemini_api",
        lambda api_key: [f"gemini-modelo-{i}" for i in range(10)]
        + ["gemini-modelo-actual"],
    )

    modelos, fuente = configuracion._modelos_gemini_cacheados("clave-prioridad", forzar=True)

    assert len(modelos) == 10
    assert modelos[0] == "gemini-modelo-actual"
    assert fuente == "api"


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


def test_configuracion_guardada_se_restablece_desde_base_de_datos(client, monkeypatch):
    guardada = guardar(client, modelo="gemini-2.5-flash").json()
    assert guardada["proveedor"] == "gemini"

    monkeypatch.setenv("LLM_PROVEEDOR", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")

    restaurada = client.get("/config").json()

    assert restaurada["proveedor"] == "gemini"
    assert restaurada["modelo"] == "gemini-2.5-flash"
    assert configuracion.estado()["privacidad"] == "mascara"


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
