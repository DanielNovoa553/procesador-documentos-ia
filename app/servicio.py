import os
import re
from pathlib import Path

from app.extractor import ExtraccionError, extraer
from app.schemas import Factura

RUTA_MOCK = Path("resultados/extracciones")


def modo() -> str:
    return os.getenv("EXTRACTOR_MODO", "mock").lower()


def modelo() -> str:
    return os.getenv("GEMINI_MODEL", "desconocido")


def etiqueta_modelo() -> str:
    return modelo() if modo() == "real" else f"simulado:{modelo()}"


def extraer_segun_modo(nombre_archivo: str, pdf_bytes: bytes) -> Factura:
    if modo() == "real":
        return extraer(pdf_bytes)

    base = re.sub(r"[^A-Za-z0-9_-]", "", Path(nombre_archivo).stem)
    ruta = RUTA_MOCK / modelo() / f"{base}.json"
    if not base or not ruta.exists():
        raise ExtraccionError(
            f"Modo simulado: no hay una extracción guardada para '{nombre_archivo}'. "
            "Usa uno de los archivos ya evaluados o cambia EXTRACTOR_MODO a real."
        )
    return Factura.model_validate_json(ruta.read_text(encoding="utf-8"))