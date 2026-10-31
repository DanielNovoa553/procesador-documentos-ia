"""Enmascaramiento de datos personales antes de enviar texto a un servicio externo.

Es una reducción de exposición, no una anonimización: solo cubre patrones conocidos
(RFC, folio fiscal, correo, teléfono), nombres y direcciones que van tras una etiqueta,
y los términos que el operador indique en PRIVACIDAD_TERMINOS.
"""
import json
import os
import re
from dataclasses import dataclass, field

CATEGORIAS = ("RFC", "UUID", "EMAIL", "TEL", "NOMBRE", "DIR", "TERM")
_TOKEN_EN_TEXTO = re.compile(r"\[(" + "|".join(CATEGORIAS) + r")_(\d+)\]")
_TOKEN_COMPLETO = re.compile(r"^\[?(" + "|".join(CATEGORIAS) + r")_(\d+)\]?$")

PATRON_UUID = re.compile(
    r"(?<![0-9A-Fa-f-])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f-])"
)
PATRON_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PATRON_RFC = re.compile(r"(?<![A-Za-z0-9])[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}(?![A-Za-z0-9])", re.IGNORECASE)
PATRON_TEL = re.compile(r"(?<![\d.,])(?:\+?52[ -]?)?\d{2}[ -]?\d{4}[ -]?\d{4}(?![\d.,])")

_FIN_DE_VALOR = r"(?=\s{3,}|$)"
ETIQUETA_NOMBRE = re.compile(
    r"(?im)(\b(?:nombre del cliente|nombre emisor|nombre receptor|nombre|cliente|raz[oó]n social)\b\s*:\s*)(.+?)"
    + _FIN_DE_VALOR
)
ETIQUETA_NOMBRE_MAYUS = re.compile(r"(?m)^(\s*(?:NOMBRE|CLIENTE)\s+)(.+?)" + _FIN_DE_VALOR)
ETIQUETA_DIR = re.compile(
    r"(?im)(\b(?:direcci[oó]n de env[ií]o|direcci[oó]n env[ií]o|direcci[oó]n|domicilio fiscal|domicilio|calle|enviar a)\b\s*:\s*)(.+?)"
    + _FIN_DE_VALOR
)


@dataclass
class Mascara:
    token_a_valor: dict = field(default_factory=dict)
    _valor_a_token: dict = field(default_factory=dict)
    _contadores: dict = field(default_factory=dict)

    def token(self, categoria: str, valor: str) -> str:
        valor = valor.strip()
        clave = (categoria, valor.upper() if categoria in ("RFC", "UUID") else valor)
        if clave not in self._valor_a_token:
            n = self._contadores.get(categoria, 0) + 1
            self._contadores[categoria] = n
            t = f"[{categoria}_{n}]"
            self._valor_a_token[clave] = t
            self.token_a_valor[t] = valor
        return self._valor_a_token[clave]


def terminos_configurados() -> list[str]:
    bruto = os.getenv("PRIVACIDAD_TERMINOS", "")
    return [t.strip() for t in bruto.split(";") if len(t.strip()) >= 3]


def enmascarar(texto: str, terminos: list[str] | None = None) -> tuple[str, Mascara]:
    mascara = Mascara()
    terminos = terminos_configurados() if terminos is None else terminos

    for termino in sorted(terminos, key=len, reverse=True):
        texto = re.sub(
            re.escape(termino), lambda m: mascara.token("TERM", m.group(0)), texto, flags=re.IGNORECASE
        )

    for categoria, patron in (
        ("UUID", PATRON_UUID),
        ("EMAIL", PATRON_EMAIL),
        ("RFC", PATRON_RFC),
        ("TEL", PATRON_TEL),
    ):
        texto = patron.sub(lambda m, c=categoria: mascara.token(c, m.group(0)), texto)

    def por_etiqueta(categoria):
        def reemplazo(m):
            valor = m.group(2)
            if _TOKEN_EN_TEXTO.search(valor):
                return m.group(0)
            return m.group(1) + mascara.token(categoria, valor)
        return reemplazo

    texto = ETIQUETA_NOMBRE.sub(por_etiqueta("NOMBRE"), texto)
    texto = ETIQUETA_NOMBRE_MAYUS.sub(por_etiqueta("NOMBRE"), texto)
    texto = ETIQUETA_DIR.sub(por_etiqueta("DIR"), texto)
    return texto, mascara


def verificar_limpio(texto: str, terminos: list[str] | None = None) -> None:
    """Falla (cierra en seguro) si en el texto a enviar queda algún patrón sensible."""
    terminos = terminos_configurados() if terminos is None else terminos
    for nombre, patron in (
        ("folio fiscal", PATRON_UUID),
        ("correo", PATRON_EMAIL),
        ("RFC", PATRON_RFC),
        ("teléfono", PATRON_TEL),
    ):
        if patron.search(texto):
            raise ValueError(f"quedó un dato sensible sin enmascarar ({nombre})")
    for termino in terminos:
        if re.search(re.escape(termino), texto, flags=re.IGNORECASE):
            raise ValueError("quedó un término protegido sin enmascarar")


def resumen(mascara: Mascara) -> dict:
    """Cuántos valores se enmascararon por categoría. Nunca incluye los valores."""
    conteo: dict = {}
    for t in mascara.token_a_valor:
        categoria = t[1:].split("_")[0]
        conteo[categoria] = conteo.get(categoria, 0) + 1
    return conteo


def restaurar_json(texto_json: str, mascara: Mascara) -> str:
    datos = json.loads(texto_json)

    def volver(x):
        if isinstance(x, str):
            m = _TOKEN_COMPLETO.match(x.strip())
            if m:
                token = f"[{m.group(1)}_{m.group(2)}]"
                if token in mascara.token_a_valor:
                    return mascara.token_a_valor[token]
            return _TOKEN_EN_TEXTO.sub(lambda mm: mascara.token_a_valor.get(mm.group(0), mm.group(0)), x)
        if isinstance(x, list):
            return [volver(i) for i in x]
        if isinstance(x, dict):
            return {k: volver(v) for k, v in x.items()}
        return x

    return json.dumps(volver(datos), ensure_ascii=False)