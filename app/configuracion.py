"""Configuración del proveedor de IA en tiempo de ejecución (variables de entorno del proceso)."""
import os
import re

import httpx

from app import extractor

GEMINI_MODELOS_BASE = ("gemini-3.5-flash-lite", "gemini-3.8-flash")
PRIVACIDAD = ("mascara", "sin_mascara")
_NOMBRE_MODELO = re.compile(r"^[A-Za-z0-9._:/-]{1,100}$")


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


def gemini_modelos() -> list[str]:
    bruto = os.getenv("GEMINI_MODELOS", "")
    modelos = [m.strip() for m in bruto.split(",") if m.strip()] or list(GEMINI_MODELOS_BASE)
    actual = os.getenv("GEMINI_MODEL", "").strip()
    if actual and actual not in modelos:
        modelos.insert(0, actual)
    return modelos


def estado() -> dict:
    proveedor = extractor.proveedor()
    return {
        "proveedor": proveedor,
        "modelo": (
            os.getenv("OLLAMA_MODEL", "llama3.1:8b")
            if proveedor == "ollama"
            else os.getenv("GEMINI_MODEL", "")
        ),
        "privacidad": "sin_mascara" if extractor.entrada_gemini() == "pdf" else "mascara",
        "ollama_modelos": ollama_modelos(),
        "gemini_modelos": gemini_modelos(),
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
