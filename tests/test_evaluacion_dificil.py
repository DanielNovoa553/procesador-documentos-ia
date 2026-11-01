import json

from pypdf import PdfReader

from app.extractor import _texto_del_pdf
from app.schemas import factura_desde_json
from scripts.evaluar_facturas_dificiles import evaluar_caso, reporte_markdown
from scripts.generar_facturas_dificiles import factura_base, generar, manifiesto


def test_generador_crea_casos_y_diferencia_escaneo_de_texto(tmp_path):
    casos = generar(tmp_path)
    por_nombre = {caso["escenario"]: caso for caso in casos}

    assert set(por_nombre) == {
        "factura_escaneada",
        "factura_rotada",
        "factura_sin_rfc",
        "factura_iva_0",
    }
    assert por_nombre["factura_sin_rfc"]["datos_esperados"]["rfc_emisor"] is None
    assert por_nombre["factura_iva_0"]["datos_esperados"]["iva"] == 0.0
    assert por_nombre["factura_iva_0"]["estado_esperado"] == "validado"
    assert por_nombre["factura_escaneada"]["error_extraccion_esperado"]
    assert PdfReader(str(tmp_path / "factura_rotada.pdf")).pages[0].rotation == 90
    assert PdfReader(str(tmp_path / "factura_escaneada.pdf")).pages[0].extract_text() in ("", None)
    texto_rotado = _texto_del_pdf((tmp_path / "factura_rotada.pdf").read_bytes())
    assert "Servicio de mantenimiento" in texto_rotado
    assert len(_texto_del_pdf((tmp_path / "factura_escaneada.pdf").read_bytes())) < 40
    assert json.loads((tmp_path / "casos.json").read_text(encoding="utf-8")) == casos


def test_evaluador_acepta_error_esperado_de_ocr():
    caso = {
        "escenario": "factura_escaneada",
        "datos_esperados": {},
        "estado_esperado": "error_extraccion_esperado",
        "motivo_esperado": None,
        "error_extraccion_esperado": "no contiene texto extraíble",
    }

    resultado = evaluar_caso(caso, None, "El PDF no contiene texto extraíble (¿es un escaneo?)")

    assert resultado["correcto"]
    assert resultado["resultado"] == "escaneo_sin_ocr"


def test_evaluador_mide_factura_con_iva_cero_y_sin_rfc():
    datos_iva = factura_base()
    datos_iva["iva"] = 0.0
    datos_iva["total"] = datos_iva["subtotal"]
    datos_sin_rfc = factura_base()
    datos_sin_rfc["rfc_emisor"] = None
    casos = {
        "factura_iva_0": manifiesto(datos_iva, "factura_iva_0"),
        "factura_sin_rfc": manifiesto(datos_sin_rfc, "factura_sin_rfc"),
    }
    factura_iva = factura_desde_json(json.dumps(datos_iva))
    factura_sin_rfc = factura_desde_json(json.dumps(datos_sin_rfc))

    assert evaluar_caso(casos["factura_iva_0"], factura_iva, None)["correcto"]
    assert evaluar_caso(casos["factura_sin_rfc"], factura_sin_rfc, None)["correcto"]


def test_reporte_identifica_proveedor_y_limite_de_ocr():
    filas = [{
        "escenario": "factura_escaneada",
        "resultado": "escaneo_sin_ocr",
        "correcto": True,
        "campos_mal": [],
        "estado": "no_aplica",
        "estado_esperado": "error_extraccion_esperado",
        "motivo_esperado": None,
        "error": "No hay texto",
    }]

    reporte = reporte_markdown(filas, "ollama", "llama3.2:3b", "local")

    assert "ollama (local)" in reporte
    assert "limitación de OCR esperada: 1 de 1" in reporte
