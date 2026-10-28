import argparse
import json
import os
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

CARPETA = Path("data/facturas")
SALIDA = Path("resultados")
load_dotenv()
MODELO = os.getenv("GEMINI_MODEL", "desconocido")
CACHE = SALIDA / "extracciones" / MODELO


def obtener_factura(nombre: str, usar_cache: bool):
    ruta_cache = CACHE / f"{nombre}.json"
    if usar_cache and ruta_cache.exists():
        return factura_desde_json(ruta_cache.read_text(encoding="utf-8")), None
    try:
        factura = extraer((CARPETA / f"{nombre}.pdf").read_bytes())
    except ExtraccionError as e:
        return None, str(e)
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta_cache.write_text(factura.model_dump_json(indent=2), encoding="utf-8")
    time.sleep(13)
    return factura, None


def pct(parte: int, total: int) -> str:
    return f"{(100 * parte / total):.1f} %" if total else "n/a"


def main():
    parser = argparse.ArgumentParser(description="Evalúa extracción y validación con las facturas de prueba")
    parser.add_argument("--cache", action="store_true",
                        help="Reutiliza las extracciones guardadas en vez de llamar a Gemini")
    parser.add_argument("--facturas", nargs="*",
                        help="Evalúa solo estas facturas, por ejemplo: factura_016 factura_020")
    args = parser.parse_args()
    load_dotenv()

    archivos = sorted(CARPETA.glob("factura_*.json"))
    if not archivos:
        raise SystemExit("No hay facturas en data/facturas. Ejecuta scripts/generar_facturas.py")

    if args.facturas:
        archivos = [a for a in archivos if a.stem in set(args.facturas)]
        if not archivos:
            raise SystemExit("Ninguna de las facturas indicadas existe en data/facturas")

    total = len(archivos)
    aciertos = {campo: 0 for campo in CAMPOS}
    filas = []

    for ruta in archivos:
        nombre = ruta.stem
        doc = json.loads(ruta.read_text(encoding="utf-8"))
        esperado = doc["datos"]
        motivo_esperado = doc["motivo_esperado"]
        factura, error = obtener_factura(nombre, args.cache)

        if error and "(429)" in error:
            print("\nSe alcanzó el límite de cuota de la API. Se detiene la evaluación.")
            print("Lo ya procesado quedó guardado: vuelve a ejecutar con --cache cuando se renueve.")
            sys.exit(1)

        fila = {
            "nombre": nombre,
            "estado_esperado": doc["estado_esperado"],
            "motivo_esperado": motivo_esperado,
            "campos_mal": list(CAMPOS),
            "estado": "error_extraccion",
            "codigos": [],
            "correcto": False,
            "error": error,
        }

        if factura is not None:
            comp = comparar(factura.model_dump(), esperado)
            for campo, ok in comp.items():
                aciertos[campo] += int(ok)
            resultado = validar(factura)
            estado_ok = resultado.estado == doc["estado_esperado"]
            motivo_ok = motivo_esperado is None or motivo_esperado in resultado.codigos
            fila.update({
                "campos_mal": [c for c, ok in comp.items() if not ok],
                "estado": resultado.estado,
                "codigos": resultado.codigos,
                "correcto": estado_ok and motivo_ok,
            })

        filas.append(fila)
        marca = "OK" if fila["correcto"] else "REVISAR"
        print(f"{nombre}  campos mal: {len(fila['campos_mal'])}  "
              f"estado: {fila['estado']} (esperado {fila['estado_esperado']})  {marca}")
        if error:
            print(f"    error de extracción: {error}")

    intencionales = [f for f in filas if f["motivo_esperado"]]
    detectadas = [f for f in intencionales if f["correcto"]]
    falsos_positivos = [f for f in filas if f["estado_esperado"] == "validado" and f["estado"] == "revision_manual"]
    con_error = [f for f in filas if f["error"]]
    correctas = [f for f in filas if f["correcto"]]
    procesadas = total - len(con_error)
    total_campos_proc = procesadas * len(CAMPOS)
    campos_ok = sum(aciertos.values())

    lineas = [
        "# Resultados de la evaluación",
        "",
        f"- Fecha: {date.today().isoformat()}",
        f"- Modelo: {os.getenv('GEMINI_MODEL')}",
        f"- Facturas evaluadas: {total} (documentos sintéticos)",
        f"- Facturas que la API procesó: {procesadas} de {total}",
        f"- Facturas con error de la API (excluidas de la precisión): {len(con_error)}",
        "",
        "## Extracción: acierto por campo (sobre las facturas procesadas)",
        "",
        "| Campo | Aciertos | Precisión |",
        "|---|---|---|",
    ]
    for campo in CAMPOS:
        lineas.append(f"| {campo} | {aciertos[campo]} de {procesadas} | {pct(aciertos[campo], procesadas)} |")
    lineas += [
        f"| **Global** | {campos_ok} de {total_campos_proc} | {pct(campos_ok, total_campos_proc)} |",
        "",
        "## Validación",
        "",
        f"- Facturas con el estado correcto: {len(correctas)} de {total} ({pct(len(correctas), total)})",
        f"- Errores intencionales detectados con el motivo correcto: {len(detectadas)} de {len(intencionales)}",
        f"- Falsos positivos (facturas buenas enviadas a revisión manual): {len(falsos_positivos)}",
    ]

    problemas = [f for f in filas if not f["correcto"] or f["campos_mal"]]
    if problemas:
        lineas += ["", "## Detalle de lo que falló", ""]
        for f in problemas:
            if f["error"]:
                lineas.append(f"- {f['nombre']}: no se pudo extraer. {f['error'][:300]}")
                continue
            partes = []
            if f["campos_mal"]:
                partes.append("campos diferentes: " + ", ".join(f["campos_mal"]))
            if not f["correcto"]:
                partes.append(f"estado {f['estado']}, esperado {f['estado_esperado']}")
                if f["codigos"]:
                    partes.append("motivos obtenidos: " + ", ".join(f["codigos"]))
                if f["motivo_esperado"]:
                    partes.append(f"motivo esperado: {f['motivo_esperado']}")
            lineas.append(f"- {f['nombre']}: " + "; ".join(partes))

    reporte = "\n".join(lineas) + "\n"
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta_reporte = SALIDA / f"evaluacion_{MODELO}.md"
    ruta_reporte.write_text(reporte, encoding="utf-8")

    print("\n" + reporte)
    print(f"Reporte guardado en {ruta_reporte}")


if __name__ == "__main__":
    main()