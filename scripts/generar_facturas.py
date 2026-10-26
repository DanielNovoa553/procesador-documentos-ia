import json
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

random.seed(42)

SALIDA = Path("data/facturas")
TOTAL_FACTURAS = 20
IVA_TASA = 0.16

ERRORES = {
    6: "total_no_coincide",
    12: "rfc_invalido",
    16: "subtotal_no_coincide_conceptos",
    20: "fecha_futura",
}

EMISORES = [
    "Comercial Norte S.A. de C.V.",
    "Servicios Alfa S.A. de C.V.",
    "Papelería Centro S.A. de C.V.",
    "Tecnologías del Valle S.A. de C.V.",
    "Distribuidora Andina S.A. de C.V.",
    "Consultoría Horizonte S.C.",
    "Transportes Rápidos del Sur S.A. de C.V.",
    "Alimentos La Cosecha S.A. de C.V.",
    "Constructora Meridiana S.A. de C.V.",
    "Estudio Creativo Luna S.C.",
]

CATALOGO = [
    ("Licencia anual de software", 800, 5000),
    ("Servicio de consultoría por hora", 400, 1200),
    ("Papel bond carta (caja)", 150, 450),
    ("Mantenimiento de equipo", 500, 2500),
    ("Flete local", 300, 1500),
    ("Capacitación en sitio", 1500, 6000),
    ("Diseño de logotipo", 1000, 4000),
    ("Tóner para impresora", 600, 1800),
    ("Hospedaje de servidor (mensual)", 200, 900),
    ("Soporte técnico mensual", 700, 2200),
]

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

ESTILOS = [
    {
        "fuente": "Helvetica", "negrita": "Helvetica-Bold", "centrado": False,
        "titulo": "FACTURA", "etq_desc": "Descripción", "etq_importe": "Importe",
        "etq_subtotal": "Subtotal", "etq_iva": "IVA 16%", "etq_total": "Total",
    },
    {
        "fuente": "Times-Roman", "negrita": "Times-Bold", "centrado": True,
        "titulo": "COMPROBANTE FISCAL", "etq_desc": "Concepto", "etq_importe": "Monto",
        "etq_subtotal": "Importe sin impuestos", "etq_iva": "Impuesto (IVA 16%)",
        "etq_total": "Total a pagar",
    },
    {
        "fuente": "Courier", "negrita": "Courier-Bold", "centrado": False,
        "titulo": "Factura de venta", "etq_desc": "Detalle", "etq_importe": "Importe",
        "etq_subtotal": "Subtotal", "etq_iva": "I.V.A.", "etq_total": "TOTAL",
    },
]

LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALFANUM = LETRAS + "0123456789"


def dinero(valor):
    return f"${valor:,.2f}"


def formatear_fecha(f, estilo):
    if estilo == 0:
        return f"{f.day:02d}/{f.month:02d}/{f.year}"
    if estilo == 1:
        return f"{f.day} de {MESES[f.month - 1]} de {f.year}"
    return f.isoformat()


def generar_rfc():
    letras = "".join(random.choice(LETRAS) for _ in range(3))
    nacimiento = date(random.randint(1995, 2015), random.randint(1, 12), random.randint(1, 28))
    homoclave = "".join(random.choice(ALFANUM) for _ in range(3))
    return f"{letras}{nacimiento:%y%m%d}{homoclave}"


def generar_datos():
    conceptos = []
    for descripcion, minimo, maximo in random.sample(CATALOGO, random.randint(1, 5)):
        cantidad = random.randint(1, 6)
        precio = round(random.uniform(minimo, maximo), 2)
        conceptos.append({
            "descripcion": descripcion,
            "cantidad": cantidad,
            "precio_unitario": precio,
            "importe": round(cantidad * precio, 2),
        })
    subtotal = round(sum(c["importe"] for c in conceptos), 2)
    iva = round(subtotal * IVA_TASA, 2)
    return {
        "emisor": random.choice(EMISORES),
        "rfc_emisor": generar_rfc(),
        "fecha": date.today() - timedelta(days=random.randint(1, 365)),
        "subtotal": subtotal,
        "iva": iva,
        "total": round(subtotal + iva, 2),
        "conceptos": conceptos,
    }


def aplicar_error(datos, tipo):
    if tipo == "total_no_coincide":
        datos["total"] = round(datos["total"] + random.choice([50, 120, 340, -75]), 2)
    elif tipo == "rfc_invalido":
        datos["rfc_emisor"] = datos["rfc_emisor"][:9]
    elif tipo == "subtotal_no_coincide_conceptos":
        datos["subtotal"] = round(datos["subtotal"] + 200, 2)
        datos["iva"] = round(datos["subtotal"] * IVA_TASA, 2)
        datos["total"] = round(datos["subtotal"] + datos["iva"], 2)
    elif tipo == "fecha_futura":
        datos["fecha"] = date.today() + timedelta(days=90)


def dibujar_pdf(ruta, d, estilo, estilo_fecha, folio):
    c = canvas.Canvas(str(ruta), pagesize=letter)
    ancho, alto = letter
    margen = 50
    fuente, negrita = estilo["fuente"], estilo["negrita"]
    fecha_txt = formatear_fecha(d["fecha"], estilo_fecha)
    y = alto - 60

    c.setFont(negrita, 16)
    if estilo["centrado"]:
        c.drawCentredString(ancho / 2, y, d["emisor"])
        c.setFont(fuente, 10)
        c.drawCentredString(ancho / 2, y - 16, f"RFC: {d['rfc_emisor']}")
        c.drawCentredString(ancho / 2, y - 32, f"{estilo['titulo']} No. {folio}")
        c.drawCentredString(ancho / 2, y - 48, f"Fecha de emisión: {fecha_txt}")
        y -= 90
    else:
        c.drawString(margen, y, d["emisor"])
        c.setFont(fuente, 10)
        c.drawString(margen, y - 16, f"RFC: {d['rfc_emisor']}")
        c.drawRightString(ancho - margen, y, f"{estilo['titulo']} No. {folio}")
        c.drawRightString(ancho - margen, y - 16, f"Fecha: {fecha_txt}")
        y -= 70

    c.setFont(negrita, 10)
    c.drawString(margen, y, estilo["etq_desc"])
    c.drawRightString(330, y, "Cant.")
    c.drawRightString(440, y, "Precio unit.")
    c.drawRightString(ancho - margen, y, estilo["etq_importe"])
    c.line(margen, y - 5, ancho - margen, y - 5)
    y -= 22

    c.setFont(fuente, 10)
    for k in d["conceptos"]:
        c.drawString(margen, y, k["descripcion"])
        c.drawRightString(330, y, str(k["cantidad"]))
        c.drawRightString(440, y, dinero(k["precio_unitario"]))
        c.drawRightString(ancho - margen, y, dinero(k["importe"]))
        y -= 18

    c.line(margen, y + 6, ancho - margen, y + 6)
    y -= 14
    filas = [
        (estilo["etq_subtotal"], d["subtotal"], fuente),
        (estilo["etq_iva"], d["iva"], fuente),
        (estilo["etq_total"], d["total"], negrita),
    ]
    for etiqueta, valor, tipo_fuente in filas:
        c.setFont(tipo_fuente, 10)
        c.drawRightString(440, y, etiqueta)
        c.drawRightString(ancho - margen, y, dinero(valor))
        y -= 18

    c.setFont(fuente, 8)
    c.drawString(margen, 40, "Documento ficticio generado con fines de prueba. Sin validez fiscal.")
    c.save()


def guardar_respuesta(ruta, nombre, d, motivo):
    esperado = {
        "archivo": f"{nombre}.pdf",
        "datos": {
            "emisor": d["emisor"],
            "rfc_emisor": d["rfc_emisor"],
            "fecha": d["fecha"].isoformat(),
            "subtotal": d["subtotal"],
            "iva": d["iva"],
            "total": d["total"],
            "conceptos": [
                {"descripcion": k["descripcion"], "cantidad": k["cantidad"], "importe": k["importe"]}
                for k in d["conceptos"]
            ],
        },
        "estado_esperado": "revision_manual" if motivo else "validado",
        "motivo_esperado": motivo,
    }
    ruta.write_text(json.dumps(esperado, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    for i in range(1, TOTAL_FACTURAS + 1):
        datos = generar_datos()
        motivo = ERRORES.get(i)
        if motivo:
            aplicar_error(datos, motivo)

        nombre = f"factura_{i:03d}"
        estilo = ESTILOS[(i - 1) % len(ESTILOS)]
        estilo_fecha = random.randint(0, 2)
        dibujar_pdf(SALIDA / f"{nombre}.pdf", datos, estilo, estilo_fecha, f"A-{1000 + i}")
        guardar_respuesta(SALIDA / f"{nombre}.json", nombre, datos, motivo)

    print(f"Listo: {TOTAL_FACTURAS} facturas en {SALIDA}")
    for i, motivo in ERRORES.items():
        print(f"  factura_{i:03d}: error intencional -> {motivo}")


if __name__ == "__main__":
    main()