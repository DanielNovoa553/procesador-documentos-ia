CAMPOS = ["emisor", "rfc_emisor", "fecha", "subtotal", "iva", "total", "conceptos"]


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