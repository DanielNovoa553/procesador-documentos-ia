import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from app.comparacion import CAMPOS, comparar
from app.extractor import ExtraccionError, extraer
from app.schemas import factura_desde_json
from app.validators import validar

load_dotenv()
RAIZ = Path(__file__).resolve().parents[1]
CARPETA = RAIZ / "data" / "facturas_dificiles"
SALIDA = RAIZ / "resultados"


def configurar(proveedor: str, modelo: str) -> str:
    if proveedor not in {"ollama", "gemini"}:
        raise ValueError("Proveedor no válido")
    os.environ["LLM_PROVEEDOR"] = proveedor
    if proveedor == "ollama":
        os.environ["OLLAMA_MODEL"] = modelo
        return "local"
    os.environ["GEMINI_MODEL"] = modelo
    os.environ["GEMINI_ENTRADA"] = "mascara"
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("Falta GEMINI_API_KEY para evaluar Gemini con máscara")
    return "mascara"


def cache_dir(proveedor: str, modelo: str, entrada: str) -> Path:
    etiqueta = re.sub(r"[^A-Za-z0-9._-]", "_", f"{proveedor}-{modelo}-{entrada}")
    return SALIDA / "extracciones_dificiles" / etiqueta


def extraer_caso(nombre: str, proveedor: str, modelo: str, entrada: str, usar_cache: bool):
    ruta_cache = cache_dir(proveedor, modelo, entrada) / f"{nombre}.json"
    if usar_cache:
        if not ruta_cache.exists():
            return None, f"No existe el resultado en caché: {ruta_cache}"
        datos_cache = json.loads(ruta_cache.read_text(encoding="utf-8"))
        if datos_cache["error"]:
            return None, datos_cache["error"]
        return factura_desde_json(json.dumps(datos_cache["factura"])), None

    try:
        factura = extraer((CARPETA / f"{nombre}.pdf").read_bytes())
    except ExtraccionError as error:
        resultado = {"factura": None, "error": str(error)}
    else:
        resultado = {"factura": factura.model_dump(), "error": None}

    ruta_cache.parent.mkdir(parents=True, exist_ok=True)
    ruta_cache.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return (factura, None) if resultado["error"] is None else (None, resultado["error"])


def evaluar_caso(caso: dict, factura, error: str | None) -> dict:
    error_esperado = caso["error_extraccion_esperado"]
    if error_esperado:
        correcto = factura is None and error is not None and error_esperado in error.lower()
        return {
            "escenario": caso["escenario"],
            "resultado": "escaneo_sin_ocr" if correcto else "fallo_inesperado",
            "correcto": correcto,
            "campos_mal": [],
            "estado": "no_aplica",
            "estado_esperado": "error_extraccion_esperado",
            "motivo_esperado": None,
            "error": error,
        }

    if error or factura is None:
        return {
            "escenario": caso["escenario"],
            "resultado": "error_extraccion",
            "correcto": False,
            "campos_mal": list(CAMPOS),
            "estado": "error_extraccion",
            "estado_esperado": caso["estado_esperado"],
            "motivo_esperado": caso["motivo_esperado"],
            "error": error,
        }

    campos = comparar(factura.model_dump(), caso["datos_esperados"])
    resultado = validar(factura)
    estado_ok = resultado.estado == caso["estado_esperado"]
    motivo_ok = caso["motivo_esperado"] is None or caso["motivo_esperado"] in resultado.codigos
    return {
        "escenario": caso["escenario"],
        "resultado": "evaluado",
        "correcto": all(campos.values()) and estado_ok and motivo_ok,
        "campos_mal": [campo for campo, ok in campos.items() if not ok],
        "estado": resultado.estado,
        "estado_esperado": caso["estado_esperado"],
        "codigos": resultado.codigos,
        "motivo_esperado": caso["motivo_esperado"],
        "error": None,
    }


def reporte_markdown(filas: list[dict], proveedor: str, modelo: str, entrada: str) -> str:
    escaneos = [fila for fila in filas if fila["resultado"] in {"escaneo_sin_ocr", "fallo_inesperado"}]
    casos_ok = sum(fila["correcto"] for fila in filas)
    lineas = [
        "# Evaluación de facturas difíciles",
        "",
        f"- Fecha: {date.today().isoformat()}",
        f"- Proveedor: {proveedor} ({entrada})",
        f"- Modelo: {modelo}",
        f"- Casos: {len(filas)}",
        f"- Casos con resultado esperado: {casos_ok} de {len(filas)}",
        "",
        "| Caso | Resultado | Estado | Campos incorrectos | Correcto |",
        "|---|---|---|---|---|",
    ]
    for fila in filas:
        incorrectos = ", ".join(fila["campos_mal"]) or "—"
        lineas.append(
            f"| {fila['escenario']} | {fila['resultado']} | {fila['estado']} "
            f"| {incorrectos} | {'sí' if fila['correcto'] else 'no'} |"
        )

    filas_con_texto = [
        fila for fila in filas if fila["resultado"] in {"evaluado", "error_extraccion"}
    ]
    if filas_con_texto:
        aciertos = {campo: 0 for campo in CAMPOS}
        for fila in filas_con_texto:
            for campo in CAMPOS:
                if campo not in fila["campos_mal"]:
                    aciertos[campo] += 1
        lineas += [
            "",
            f"## Extracción de los casos con texto ({len(filas_con_texto)} casos)",
            "",
            "| Campo | Aciertos | Precisión |",
            "|---|---:|---:|",
        ]
        for campo in CAMPOS:
            lineas.append(
                f"| {campo} | {aciertos[campo]} de {len(filas_con_texto)} "
                f"| {100 * aciertos[campo] / len(filas_con_texto):.1f} % |"
            )

    lineas += [
        "",
        "## Interpretación",
        "",
        f"- Escaneos con la limitación de OCR esperada: {sum(f['correcto'] for f in escaneos)} de {len(escaneos)}.",
        "- Una extracción fallida en el caso escaneado es el comportamiento esperado: la aplicación aún no incluye OCR.",
        "- Los documentos son sintéticos; estos resultados no sustituyen una prueba con facturas reales.",
    ]
    errores = [fila for fila in filas if fila["error"]]
    if errores:
        lineas += ["", "## Errores", ""]
        for fila in errores:
            lineas.append(f"- {fila['escenario']}: {fila['error']}")
    return "\n".join(lineas) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evalúa casos difíciles de facturas en Ollama local o Gemini con máscara."
    )
    parser.add_argument("--proveedor", choices=("ollama", "gemini"), required=True)
    parser.add_argument("--modelo", help="Modelo a evaluar; por defecto usa la variable de entorno")
    parser.add_argument("--cache", action="store_true", help="Reutiliza resultados de una ejecución anterior")
    parser.add_argument("--pausa", type=float, help="Espera entre solicitudes; por defecto 13 s para Gemini y 0 para Ollama")
    args = parser.parse_args()
    load_dotenv()

    modelo = args.modelo or os.getenv("OLLAMA_MODEL" if args.proveedor == "ollama" else "GEMINI_MODEL")
    if not modelo:
        raise SystemExit("Indica --modelo o configura el modelo en .env")
    try:
        entrada = configurar(args.proveedor, modelo)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    manifiesto = CARPETA / "casos.json"
    if not manifiesto.exists():
        raise SystemExit("No se encontró el conjunto de casos. Ejecuta scripts/generar_facturas_dificiles.py")
    casos = json.loads(manifiesto.read_text(encoding="utf-8"))
    pausa = args.pausa if args.pausa is not None else (13 if args.proveedor == "gemini" else 0)
    filas = []

    for indice, caso in enumerate(casos):
        factura, error = extraer_caso(
            caso["escenario"], args.proveedor, modelo, entrada, args.cache
        )
        fila = evaluar_caso(caso, factura, error)
        filas.append(fila)
        marca = "OK" if fila["correcto"] else "REVISAR"
        print(
            f"{caso['escenario']}: {fila['resultado']}; "
            f"estado={fila['estado']} (esperado {fila['estado_esperado']}); {marca}"
        )
        if error:
            print(f"  {error}")
        if pausa and indice < len(casos) - 1 and not args.cache:
            time.sleep(pausa)

    reporte = reporte_markdown(filas, args.proveedor, modelo, entrada)
    SALIDA.mkdir(parents=True, exist_ok=True)
    etiqueta = re.sub(r"[^A-Za-z0-9._-]", "_", f"{args.proveedor}-{modelo}-{entrada}")
    ruta_reporte = SALIDA / f"evaluacion_dificiles_{etiqueta}.md"
    ruta_reporte.write_text(reporte, encoding="utf-8")
    print(f"\nReporte guardado en {ruta_reporte}")
    if any(not fila["correcto"] for fila in filas):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
