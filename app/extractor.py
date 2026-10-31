import io
import logging
import os
import re
import time

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pypdf import PdfReader

from app import privacidad
from app.schemas import Factura, factura_desde_json

load_dotenv()

logger = logging.getLogger("uvicorn.error")

TIEMPO_LIMITE_MS = 60_000
TIEMPO_LIMITE_OLLAMA_S = 300

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
- clave_prod_serv es la clave del catálogo del SAT (código numérico de 8 dígitos). no_identificacion es el código interno del producto que asigna el emisor, como el de la columna "Clave" de una nota de venta (por ejemplo ADP4). Si el documento solo trae un código corto del emisor, ponlo en no_identificacion y deja clave_prod_serv en null.
- No incluyas sellos digitales, la cadena original ni datos del certificado."""


class ExtraccionError(Exception):
    pass


def proveedor() -> str:
    return os.getenv("LLM_PROVEEDOR", "gemini").strip().lower()


def es_local() -> bool:
    return proveedor() == "ollama"


ENTRADAS = ("pdf", "texto", "mascara")
SUFIJOS = {"pdf": "", "texto": "-texto", "mascara": "-mascara"}

AVISO_MASCARA = (
    "El texto fue anonimizado: algunos datos personales se reemplazaron por marcadores con el formato "
    "[CATEGORIA_n], por ejemplo [RFC_1] o [NOMBRE_2]. Si un campo corresponde a un dato reemplazado, "
    "devuelve el marcador tal cual, sin modificarlo, sin quitar los corchetes y sin inventar su contenido. "
    "Usa las etiquetas y el contexto del documento para decidir qué marcador corresponde al emisor y cuál al receptor."
)


def entrada_gemini() -> str:
    return os.getenv("GEMINI_ENTRADA", "pdf").strip().lower()


def nombre_modelo() -> str:
    if proveedor() == "ollama":
        modelo = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        return "ollama-" + re.sub(r"[^A-Za-z0-9._-]", "_", modelo)
    modelo = os.getenv("GEMINI_MODEL", "desconocido")
    return modelo + SUFIJOS.get(entrada_gemini(), "")


def _prompt_con_texto(texto: str, enmascarado: bool = False) -> str:
    aviso = ("\n\n" + AVISO_MASCARA) if enmascarado else ""
    return PROMPT + aviso + "\n\nTexto extraído del documento (el orden puede estar desordenado):\n\n" + texto


# ---------------------------------------------------------------- Gemini

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


def _extraer_gemini(pdf_bytes: bytes, reintentos: int = 1) -> Factura:
    modelo = os.getenv("GEMINI_MODEL")
    if not modelo:
        raise ExtraccionError("Falta GEMINI_MODEL en el archivo .env")

    entrada = entrada_gemini()
    if entrada not in ENTRADAS:
        raise ExtraccionError(f"GEMINI_ENTRADA no válida: '{entrada}'. Usa 'pdf', 'texto' o 'mascara'.")

    mascara = None
    if entrada == "pdf":
        contenido = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), PROMPT]
    else:
        texto_pdf = _limpiar_texto(_texto_del_pdf(pdf_bytes))
        if len(texto_pdf) < 40:
            raise ExtraccionError(
                "El PDF no contiene texto extraíble (¿es un escaneo?). "
                f"Con GEMINI_ENTRADA={entrada} no se envía el PDF."
            )
        if entrada == "mascara":
            try:
                texto_pdf, mascara = privacidad.enmascarar(texto_pdf)
                privacidad.verificar_limpio(texto_pdf)
            except ValueError as e:
                raise ExtraccionError(
                    f"El enmascaramiento no fue seguro; no se envió nada a Gemini: {e}"
                ) from e
            logger.info("Datos enmascarados antes de enviar: %s", privacidad.resumen(mascara))
        contenido = [_prompt_con_texto(texto_pdf, enmascarado=mascara is not None)]

    cliente = _obtener_cliente()
    respuesta = None

    for intento in range(reintentos + 1):
        try:
            logger.info("Llamando a Gemini (%s, entrada %s), intento %d...", modelo, entrada, intento + 1)
            inicio = time.perf_counter()
            respuesta = cliente.models.generate_content(
                model=modelo,
                contents=contenido,
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
            if e.code in (500, 503, 504) and intento < reintentos:
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
        if mascara is not None:
            texto = privacidad.restaurar_json(texto, mascara)
        return factura_desde_json(texto)
    except ValueError as e:
        raise ExtraccionError(f"La respuesta no cumple el esquema: {e}") from e


# ---------------------------------------------------------------- Ollama (local)

def _texto_del_pdf(pdf_bytes: bytes) -> str:
    try:
        lector = PdfReader(io.BytesIO(pdf_bytes))
        paginas = []
        for pagina in lector.pages:
            try:
                paginas.append(pagina.extract_text(extraction_mode="layout") or "")
            except TypeError:
                paginas.append(pagina.extract_text() or "")
    except Exception as e:
        raise ExtraccionError(f"No se pudo leer el PDF: {e}") from e
    return "\n".join(paginas)


def _limpiar_texto(texto: str) -> str:
    lineas = []
    for linea in texto.splitlines():
        linea = re.sub(r"[ \t]{3,}", "   ", linea).strip()
        if not linea:
            continue
        if len(linea) > 60 and " " not in linea:
            continue  # sellos digitales y cadena original: ruido que no se necesita
        lineas.append(linea)
    return "\n".join(lineas)


def _extraer_ollama(pdf_bytes: bytes) -> Factura:
    modelo = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

    texto = _limpiar_texto(_texto_del_pdf(pdf_bytes))
    if len(texto) < 40:
        raise ExtraccionError(
            "El PDF no contiene texto extraíble (¿es un escaneo?). El proveedor local no hace OCR."
        )

    cuerpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": _prompt_con_texto(texto)}],
        "format": Factura.model_json_schema(),
        "stream": False,
        "options": {"temperature": 0, "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "8192"))},
    }

    logger.info("Llamando a Ollama (%s) en local...", modelo)
    inicio = time.perf_counter()
    try:
        r = httpx.post(f"{url}/api/chat", json=cuerpo, timeout=TIEMPO_LIMITE_OLLAMA_S)
    except httpx.ConnectError as e:
        raise ExtraccionError(
            f"No se pudo conectar con Ollama en {url}. ¿Está corriendo? Prueba 'ollama list'."
        ) from e
    except httpx.HTTPError as e:
        raise ExtraccionError(f"Error al hablar con Ollama ({type(e).__name__}): {e}") from e

    if r.status_code == 404:
        raise ExtraccionError(f"Ollama no tiene el modelo '{modelo}'. Descárgalo con: ollama pull {modelo}")
    if r.status_code != 200:
        raise ExtraccionError(f"Ollama respondió {r.status_code}: {r.text[:200]}")
    logger.info("Ollama respondió en %.1f s", time.perf_counter() - inicio)

    contenido = (r.json().get("message") or {}).get("content", "")
    if not contenido:
        raise ExtraccionError("Ollama devolvió una respuesta vacía")
    try:
        factura = factura_desde_json(contenido)
    except ValueError as e:
        raise ExtraccionError(f"La respuesta no cumple el esquema: {e}") from e
    _completar_claves(factura, texto)
    return factura


def _completar_claves(factura: Factura, texto: str) -> None:
    """Los modelos locales pequeños suelen omitir la clave SAT; si el texto trae una por concepto, se recupera."""
    if all(c.clave_prod_serv for c in factura.conceptos):
        return
    claves = re.findall(r"(?m)^\s*(\d{8})\s{2,}\S", texto)
    if len(claves) != len(factura.conceptos):
        return
    for concepto, clave in zip(factura.conceptos, claves):
        if not concepto.clave_prod_serv:
            concepto.clave_prod_serv = clave


# ---------------------------------------------------------------- Punto de entrada

def extraer(pdf_bytes: bytes) -> Factura:
    elegido = proveedor()
    if elegido == "ollama":
        return _extraer_ollama(pdf_bytes)
    if elegido == "gemini":
        return _extraer_gemini(pdf_bytes)
    raise ExtraccionError(f"LLM_PROVEEDOR no válido: '{elegido}'. Usa 'gemini' u 'ollama'.")