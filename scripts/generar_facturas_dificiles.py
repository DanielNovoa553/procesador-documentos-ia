import argparse
import json
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

SALIDA = Path("data/facturas_dificiles")
FUENTE = Path(__import__("reportlab").__file__).resolve().parent / "fonts" / "Vera.ttf"


def factura_base() -> dict:
    return {
        "emisor": "Servicios Prueba Norte S.A. de C.V.",
        "rfc_emisor": "SPN010203AB1",
        "fecha": (date.today() - timedelta(days=10)).isoformat(),
        "subtotal": 1000.0,
        "iva": 160.0,
        "total": 1160.0,
        "conceptos": [
            {"descripcion": "Servicio de mantenimiento", "cantidad": 1, "importe": 1000.0}
        ],
    }


def dibujar_factura(ruta: Path, datos: dict, rotacion: int = 0) -> None:
    pdf = canvas.Canvas(str(ruta), pagesize=letter)
    if rotacion:
        pdf.setPageRotation(rotacion)
    ancho, alto = letter
    y = alto - 70
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(55, y, datos["emisor"])
    pdf.setFont("Helvetica", 11)
    y -= 26
    if datos.get("rfc_emisor"):
        pdf.drawString(55, y, f"RFC emisor: {datos['rfc_emisor']}")
        y -= 20
    pdf.drawString(55, y, f"Fecha de emisión: {datos['fecha']}")
    y -= 45
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(55, y, "Descripción")
    pdf.drawRightString(ancho - 55, y, "Importe")
    pdf.setFont("Helvetica", 11)
    for concepto in datos["conceptos"]:
        y -= 24
        pdf.drawString(55, y, concepto["descripcion"])
        pdf.drawRightString(ancho - 55, y, f"${concepto['importe']:,.2f}")
    y -= 42
    pdf.drawRightString(ancho - 150, y, "Subtotal:")
    pdf.drawRightString(ancho - 55, y, f"${datos['subtotal']:,.2f}")
    y -= 20
    pdf.drawRightString(ancho - 150, y, "IVA:")
    pdf.drawRightString(ancho - 55, y, f"${datos['iva']:,.2f}")
    y -= 20
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(ancho - 150, y, "Total:")
    pdf.drawRightString(ancho - 55, y, f"${datos['total']:,.2f}")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(55, 45, "Documento ficticio generado para evaluación. Sin validez fiscal.")
    pdf.save()


def dibujar_escaneo(ruta: Path, datos: dict) -> None:
    imagen = Image.new("RGB", (1275, 1650), "white")
    dibujo = ImageDraw.Draw(imagen)
    fuente = ImageFont.truetype(str(FUENTE), 34)
    fuente_titulo = ImageFont.truetype(str(FUENTE), 42)
    lineas = [
        datos["emisor"],
        f"RFC emisor: {datos['rfc_emisor']}",
        f"Fecha de emisión: {datos['fecha']}",
        "Descripción                         Importe",
        f"{datos['conceptos'][0]['descripcion']}              $1,000.00",
        "Subtotal:                                  $1,000.00",
        "IVA:                                          $160.00",
        "Total:                                      $1,160.00",
        "Documento ficticio de evaluación",
    ]
    y = 160
    for indice, linea in enumerate(lineas):
        fuente_actual = fuente_titulo if indice == 0 else fuente
        dibujo.text((110, y), linea, fill="#111111", font=fuente_actual)
        y += 145

    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    pdf = canvas.Canvas(str(ruta), pagesize=letter)
    pdf.drawImage(ImageReader(BytesIO(buffer.getvalue())), 0, 0, width=letter[0], height=letter[1])
    pdf.save()


def manifiesto(datos: dict, escenario: str, error_esperado: str | None = None) -> dict:
    return {
        "escenario": escenario,
        "archivo": f"{escenario}.pdf",
        "datos_esperados": datos,
        "estado_esperado": (
            "revision_manual" if datos.get("rfc_emisor") is None else "validado"
        ),
        "motivo_esperado": "campo_faltante" if datos.get("rfc_emisor") is None else None,
        "error_extraccion_esperado": error_esperado,
    }


def generar(salida: Path = SALIDA) -> list[dict]:
    salida.mkdir(parents=True, exist_ok=True)
    casos = []

    datos = factura_base()
    dibujar_escaneo(salida / "factura_escaneada.pdf", datos)
    casos.append(manifiesto(datos, "factura_escaneada", "no contiene texto extraíble"))

    datos = factura_base()
    dibujar_factura(salida / "factura_rotada.pdf", datos, rotacion=90)
    casos.append(manifiesto(datos, "factura_rotada"))

    datos = factura_base()
    datos["rfc_emisor"] = None
    dibujar_factura(salida / "factura_sin_rfc.pdf", datos)
    casos.append(manifiesto(datos, "factura_sin_rfc"))

    datos = factura_base()
    datos["iva"] = 0.0
    datos["total"] = datos["subtotal"]
    dibujar_factura(salida / "factura_iva_0.pdf", datos)
    casos.append(manifiesto(datos, "factura_iva_0"))

    (salida / "casos.json").write_text(
        json.dumps(casos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return casos


def main() -> None:
    argparse.ArgumentParser(
        description="Genera facturas sintéticas para evaluar casos difíciles."
    ).parse_args()
    casos = generar()
    print(f"Generados {len(casos)} casos sintéticos en {SALIDA}")
    for caso in casos:
        esperado = "error de OCR esperado" if caso["error_extraccion_esperado"] else "extracción evaluable"
        print(f"  {caso['escenario']}: {esperado}")


if __name__ == "__main__":
    main()
