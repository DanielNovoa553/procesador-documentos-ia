import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extractor import ExtraccionError, extraer

CARPETA = Path("data/facturas")
POR_DEFECTO = ["factura_001", "factura_002", "factura_003", "factura_006"]


def normalizar(texto):
    return " ".join(str(texto).split()).lower() if texto is not None else None


def numeros_iguales(a, b):
    return a is not None and b is not None and abs(float(a) - float(b)) < 0.01


def comparar(extraido: dict, esperado: dict) -> dict:
    resultado = {
        "emisor": normalizar(extraido["emisor"]) == normalizar(esperado["emisor"]),
        "rfc_emisor": normalizar(extraido["rfc_emisor"]) == normalizar(esperado["rfc_emisor"]),
        "fecha": extraido["fecha"] == esperado["fecha"],
        "subtotal": numeros_iguales(extraido["subtotal"], esperado["subtotal"]),
        "iva": numeros_iguales(extraido["iva"], esperado["iva"]),
        "total": numeros_iguales(extraido["total"], esperado["total"]),
    }
    ext, esp = extraido["conceptos"], esperado["conceptos"]
    resultado["conceptos"] = len(ext) == len(esp) and all(
        normalizar(a["descripcion"]) == normalizar(b["descripcion"])
        and numeros_iguales(a["cantidad"], b["cantidad"])
        and numeros_iguales(a["importe"], b["importe"])
        for a, b in zip(ext, esp)
    )
    return resultado


def main():
    nombres = sys.argv[1:] or POR_DEFECTO
    correctos = 0
    total_campos = 0

    for nombre in nombres:
        pdf = CARPETA / f"{nombre}.pdf"
        esperado = json.loads((CARPETA / f"{nombre}.json").read_text(encoding="utf-8"))["datos"]

        print(f"\n=== {nombre} ===")
        try:
            factura = extraer(pdf.read_bytes())
        except ExtraccionError as e:
            print("ERROR:", e)
            continue

        extraido = factura.model_dump()
        for campo, ok in comparar(extraido, esperado).items():
            total_campos += 1
            correctos += ok
            print(f"  {campo:<11} {'OK' if ok else 'DIFERENTE'}")
            if not ok and campo != "conceptos":
                print(f"      esperado: {esperado[campo]}")
                print(f"      extraído: {extraido[campo]}")

        if not comparar(extraido, esperado)["conceptos"]:
            print("  conceptos esperados:", json.dumps(esperado["conceptos"], ensure_ascii=False))
            print("  conceptos extraídos:", json.dumps(extraido["conceptos"], ensure_ascii=False))

        time.sleep(1)

    if total_campos:
        print(f"\nResumen: {correctos} de {total_campos} campos correctos")


if __name__ == "__main__":
    main()