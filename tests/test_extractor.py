import json
from types import SimpleNamespace

import pytest

from app import extractor, privacidad
from app.extractor import ExtraccionError

TEXTO = (
    "RFC emisor:   ZZZA010101AB1\n"
    "Nombre receptor:   ANA PAULA REYES MONTERO\n"
    "1.00 H87 CONSULTA 954.00   Total 954.00"
)


class ClienteFalso:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.recibido = None
        self.models = self

    def generate_content(self, *, contents, **kwargs):
        self.recibido = contents
        return SimpleNamespace(text=self.respuesta)


def test_gemini_mascara_no_envia_datos_sensibles_y_los_restaura(monkeypatch):
    monkeypatch.setenv("LLM_PROVEEDOR", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("GEMINI_ENTRADA", "mascara")
    monkeypatch.setattr(
        extractor,
        "_texto_del_pdf",
        lambda pdf: "RFC emisor:   ZZZA010101AB1\nNombre receptor:   ANA PAULA REYES MONTERO\n"
        "1.00 H87 CONSULTA 954.00   Total 954.00",
    )
    respuesta = json.dumps({
        "emisor": "Comercial Aurora", "rfc_emisor": "[RFC_1]", "nombre_receptor": "[NOMBRE_1]",
        "fecha": "2026-01-15", "subtotal": 954.0, "iva": 0.0, "total": 954.0,
        "conceptos": [{"descripcion": "CONSULTA", "cantidad": 1, "importe": 954.0}],
    })
    cliente = ClienteFalso(respuesta)
    monkeypatch.setattr(extractor, "_obtener_cliente", lambda: cliente)

    factura = extractor.extraer(b"%PDF-1.4")

    enviado = cliente.recibido[0]
    assert "ZZZA010101AB1" not in enviado and "ANA PAULA" not in enviado
    assert isinstance(enviado, str) and len(cliente.recibido) == 1
    assert factura.rfc_emisor == "ZZZA010101AB1"
    assert factura.nombre_receptor == "ANA PAULA REYES MONTERO"
    assert extractor.nombre_modelo() == "gemini-3.8-flash-mascara"


def test_si_el_enmascaramiento_falla_no_se_llama_a_gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVEEDOR", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("GEMINI_ENTRADA", "mascara")
    monkeypatch.setattr(extractor, "_texto_del_pdf", lambda pdf: TEXTO)

    def falla(texto, terminos=None):
        raise ValueError("quedó un dato sensible sin enmascarar (RFC)")

    monkeypatch.setattr(privacidad, "verificar_limpio", falla)
    cliente = ClienteFalso("{}")
    monkeypatch.setattr(extractor, "_obtener_cliente", lambda: cliente)

    with pytest.raises(ExtraccionError, match="no se envió nada"):
        extractor.extraer(b"%PDF-1.4")
    assert cliente.recibido is None