import logging
import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from app.schemas import Factura, factura_desde_json

logger = logging.getLogger("uvicorn.error")
load_dotenv()

PROMPT = """Eres un sistema de extracción de datos de facturas, incluidas las facturas electrónicas mexicanas (CFDI). Lee el documento y devuelve los datos solicitados.

Reglas generales:
- Transcribe exactamente lo que está impreso. No calcules, no corrijas y no completes ningún valor, aunque los montos no cuadren entre sí.
- Si un dato no aparece en el documento, devuelve null. No lo inventes.
- Los montos son números, sin símbolo de moneda ni separador de miles.
- La fecha va en formato AAAA-MM-DD y es solo la fecha de emisión, sin la hora. Las fechas escritas solo con números están en formato día/mes/año.
- Los RFC van tal como aparecen, sin espacios ni guiones.
- Los conceptos van en el mismo orden en que aparecen.

Datos específicos:
- emisor y rfc_emisor son los de quien emite la factura. nombre_receptor y rfc_receptor son los de quien la recibe. No los confundas.
- folio_fiscal es el identificador UUID (36 caracteres con guiones). No lo confundas con folio, que es el número consecutivo del emisor, ni con serie, que es la letra o código que lo acompaña.
- lugar_expedicion es el código postal del lugar de emisión; codigo_postal_receptor es el del receptor.
- Los campos de texto como regimen_fiscal_emisor, regimen_fiscal_receptor, uso_cfdi, tipo_comprobante, exportacion, moneda, forma_pago, metodo_pago, unidad y objeto_impuesto van tal como aparecen impresos.
- No incluyas sellos digitales, la cadena original ni datos del certificado."""


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



load_dotenv()

logger = logging.getLogger("uvicorn.error")

TIEMPO_LIMITE_MS = 60_000

PROMPT = """Eres un sistema de extracción de datos de facturas, incluidas las facturas electrónicas mexicanas (CFDI). Lee el documento y devuelve los datos solicitados.

Reglas generales:
- Transcribe exactamente lo que está impreso. No calcules, no corrijas y no completes ningún valor, aunque los montos no cuadren entre sí.
- Si un dato no aparece en el documento, devuelve null. No lo inventes.
- Los montos son números, sin símbolo de moneda ni separador de miles.
- La fecha va en formato AAAA-MM-DD y es solo la fecha de emisión, sin la hora. Las fechas escritas solo con números están en formato día/mes/año.
- Los RFC van tal como aparecen, sin espacios ni guiones.
- Los conceptos van en el mismo orden en que aparecen.

Datos específicos:
- emisor y rfc_emisor son los de quien emite la factura. nombre_receptor y rfc_receptor son los de quien la recibe. No los confundas.
- folio_fiscal es el identificador UUID (36 caracteres con guiones). No lo confundas con folio, que es el número consecutivo del emisor, ni con serie, que es la letra o código que lo acompaña.
- lugar_expedicion es el código postal del lugar de emisión; codigo_postal_receptor es el del receptor.
- Los campos de texto como regimen_fiscal_emisor, regimen_fiscal_receptor, uso_cfdi, tipo_comprobante, exportacion, moneda, forma_pago, metodo_pago, unidad y objeto_impuesto van tal como aparecen impresos.
- No incluyas sellos digitales, la cadena original ni datos del certificado."""


class ExtraccionError(Exception):
    pass


_client = None


def _obtener_cliente():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ExtraccionError("Falta GEMINI_API_KEY en el archivo .env")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=TIEMPO_LIMITE_MS),
        )
    return _client


def extraer(pdf_bytes: bytes, reintentos: int = 1) -> Factura:
    modelo = os.getenv("GEMINI_MODEL")
    if not modelo:
        raise ExtraccionError("Falta GEMINI_MODEL en el archivo .env")

    cliente = _obtener_cliente()
    respuesta = None

    for intento in range(reintentos + 1):
        try:
            logger.info("Llamando a Gemini (%s), intento %d...", modelo, intento + 1)
            inicio = time.perf_counter()
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
            logger.info("Gemini respondió en %.1f s", time.perf_counter() - inicio)
            break
        except errors.APIError as e:
            logger.warning("Gemini devolvió un error %s", e.code)
            if e.code in (500, 503) and intento < reintentos:
                time.sleep(15 * (intento + 1))
                continue
            raise ExtraccionError(f"Error de la API de Gemini ({e.code}): {e.message}") from e
        except Exception as e:
            raise ExtraccionError(
                f"No se pudo contactar a Gemini ({type(e).__name__}): {e}"
            ) from e

    texto = respuesta.text if respuesta else None
    if not texto:
        raise ExtraccionError("Gemini devolvió una respuesta vacía")

    try:
        return factura_desde_json(texto)
    except ValueError as e:
        raise ExtraccionError(f"La respuesta no cumple el esquema: {e}") from e