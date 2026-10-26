import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.schemas import Factura

load_dotenv()

PROMPT = """Eres un sistema de extracción de datos de facturas. Lee el documento y devuelve los datos solicitados.

Reglas:
- Transcribe exactamente lo que está impreso. No calcules, no corrijas y no completes ningún valor, aunque los montos no cuadren entre sí.
- Si un dato no aparece en el documento, devuelve null. No lo inventes.
- Los montos son números, sin símbolo de moneda ni separador de miles.
- La fecha va en formato AAAA-MM-DD. Las fechas escritas solo con números están en formato día/mes/año.
- El RFC va tal como aparece, sin espacios ni guiones.
- Los conceptos van en el mismo orden en que aparecen."""


class ExtraccionError(Exception):
    pass


_client = None


def _obtener_cliente():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ExtraccionError("Falta GEMINI_API_KEY en el archivo .env")
        _client = genai.Client(api_key=api_key)
    return _client


def extraer(pdf_bytes: bytes, reintentos: int = 2) -> Factura:
    modelo = os.getenv("GEMINI_MODEL")
    if not modelo:
        raise ExtraccionError("Falta GEMINI_MODEL en el archivo .env")

    cliente = _obtener_cliente()
    respuesta = None

    for intento in range(reintentos + 1):
        try:
            respuesta = cliente.models.generate_content(
                model=modelo,
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Factura,
                    temperature=0,
                ),
            )
            break
        except errors.APIError as e:
            if e.code in (429, 500, 503) and intento < reintentos:
                time.sleep(2 ** (intento + 1))
                continue
            raise ExtraccionError(f"Error de la API de Gemini ({e.code}): {e.message}") from e

    texto = respuesta.text if respuesta else None
    if not texto:
        raise ExtraccionError("Gemini devolvió una respuesta vacía")

    try:
        return Factura.model_validate_json(texto)
    except ValidationError as e:
        raise ExtraccionError(f"La respuesta no cumple el esquema: {e}") from e