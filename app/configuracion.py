"""Configuración del proveedor de IA en tiempo de ejecución (variables de entorno del proceso)."""
import logging
import os
import re
import time

import httpx
from google import genai
from google.genai import errors, types

from app import extractor

logger = logging.getLogger("uvicorn.error")

GEMINI_MODELOS_BASE = ("gemini-3.5-flash-lite", "gemini-3.8-flash")
GEMINI_MODELOS_LIMITE = 10
GEMINI_MODELOS_CACHE_S = 300
PRIVACIDAD = ("mascara", "sin_mascara")
_NOMBRE_MODELO = re.compile(r"^[A-Za-z0-9._:/-]{1,100}$")
_gemini_cache: dict[str, tuple[float, list[str], str]] = {}


class ConfiguracionError(Exception):
    pass


def ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def ollama_modelos() -> list[str]:
    try:
        r = httpx.get(f"{ollama_url()}/api/tags", timeout=3)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def _listar_modelos_gemini_api(api_key: str) -> list[str]:
    cliente = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=8_000),
    )
    disponibles = []
    for modelo in cliente.models.list():
        if "generateContent" not in (modelo.supported_actions or []):
            continue
        nombre = (modelo.name or "").removeprefix("models/")
        if nombre.startswith("gemini-") and nombre not in disponibles:
            disponibles.append(nombre)
    return disponibles


def _modelos_gemini_cacheados(api_key: str, forzar: bool = False) -> tuple[list[str], str]:
    ahora = time.monotonic()
    cache = _gemini_cache.get(api_key)
    if not forzar and cache and cache[0] > ahora:
        return cache[1].copy(), cache[2]

    try:
        modelos = _listar_modelos_gemini_api(api_key)
    except (errors.APIError, httpx.HTTPError, ValueError) as e:
        logger.warning("No se pudo consultar la lista de modelos de Gemini (%s)", type(e).__name__)
        aviso = "No se pudo consultar Gemini; se muestra la lista configurada."
        _gemini_cache[api_key] = (ahora + 60, [], aviso)
        return [], aviso

    if not modelos:
        aviso = "La API no devolvió modelos compatibles; se muestra la lista configurada."
        _gemini_cache[api_key] = (ahora + 60, [], aviso)
        return [], aviso

    actual = os.getenv("GEMINI_MODEL", "").strip()
    if actual in modelos:
        seleccion = [actual] + [modelo for modelo in modelos if modelo != actual]
        seleccion = seleccion[:GEMINI_MODELOS_LIMITE]
    else:
        seleccion = modelos[:GEMINI_MODELOS_LIMITE]
    _gemini_cache[api_key] = (
        ahora + GEMINI_MODELOS_CACHE_S,
        seleccion.copy(),
        "api",
    )
    return seleccion, "api"


def gemini_modelos() -> list[str]:
    return _gemini_modelos_info()[0]


def _gemini_modelos_info() -> tuple[list[str], str, str | None]:
    bruto = os.getenv("GEMINI_MODELOS", "")
    modelos_configurados = [m.strip() for m in bruto.split(",") if m.strip()]
    actual = os.getenv("GEMINI_MODEL", "").strip()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if api_key:
        modelos_api, estado_api = _modelos_gemini_cacheados(api_key)
        if estado_api == "api":
            return modelos_api, "api", None
    else:
        estado_api = "Configura GEMINI_API_KEY para consultar los modelos disponibles."

    modelos = list(dict.fromkeys(modelos_configurados or GEMINI_MODELOS_BASE))
    if actual and actual not in modelos:
        modelos.insert(0, actual)
    return modelos[:GEMINI_MODELOS_LIMITE], "configuracion", estado_api


def estado() -> dict:
    proveedor = extractor.proveedor()
    gemini_disponibles, gemini_fuente, gemini_aviso = _gemini_modelos_info()
    return {
        "proveedor": proveedor,
        "modelo": (
            os.getenv("OLLAMA_MODEL", "llama3.1:8b")
            if proveedor == "ollama"
            else os.getenv("GEMINI_MODEL", "")
        ),
        "privacidad": "sin_mascara" if extractor.entrada_gemini() == "pdf" else "mascara",
        "ollama_modelos": ollama_modelos(),
        "gemini_modelos": gemini_disponibles,
        "gemini_modelos_fuente": gemini_fuente,
        "gemini_modelos_aviso": gemini_aviso,
        "gemini_api_key": bool(os.getenv("GEMINI_API_KEY")),
    }


def aplicar(proveedor: str, modelo: str, privacidad: str, acepta_riesgo: bool) -> dict:
    proveedor = proveedor.strip().lower()
    modelo = modelo.strip()
    if proveedor not in ("gemini", "ollama"):
        raise ConfiguracionError("Proveedor no válido: usa 'gemini' u 'ollama'")
    if not _NOMBRE_MODELO.match(modelo):
        raise ConfiguracionError("Nombre de modelo no válido")

    if proveedor == "ollama":
        instalados = ollama_modelos()
        if not instalados:
            raise ConfiguracionError(
                f"No se pudo consultar Ollama en {ollama_url()}. ¿Está corriendo?"
            )
        if modelo not in instalados:
            raise ConfiguracionError(f"El modelo '{modelo}' no está instalado en Ollama")
        os.environ["LLM_PROVEEDOR"] = "ollama"
        os.environ["OLLAMA_MODEL"] = modelo
        return estado()

    if privacidad not in PRIVACIDAD:
        raise ConfiguracionError("Privacidad no válida: usa 'mascara' o 'sin_mascara'")
    if modelo not in gemini_modelos():
        raise ConfiguracionError(f"El modelo '{modelo}' no está en la lista de Gemini disponibles")
    if not os.getenv("GEMINI_API_KEY"):
        raise ConfiguracionError("Falta GEMINI_API_KEY en el archivo .env")
    if privacidad == "sin_mascara" and not acepta_riesgo:
        raise ConfiguracionError(
            "Para enviar el PDF completo a Gemini debes aceptar explícitamente los riesgos de privacidad"
        )
    os.environ["LLM_PROVEEDOR"] = "gemini"
    os.environ["GEMINI_MODEL"] = modelo
    os.environ["GEMINI_ENTRADA"] = "mascara" if privacidad == "mascara" else "pdf"
    return estado()
