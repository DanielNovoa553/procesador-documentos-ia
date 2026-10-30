import re
from dataclasses import dataclass, field
from datetime import date

from app.schemas import Factura

TASA_IVA = 0.16
TOLERANCIA = 0.02
TOLERANCIA_CONCEPTO = 0.05
PATRON_RFC = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
PATRON_UUID = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
CAMPOS_OBLIGATORIOS = ["emisor", "rfc_emisor", "fecha", "subtotal", "total"]


@dataclass
class Motivo:
    codigo: str
    detalle: str


@dataclass
class ResultadoValidacion:
    estado: str
    motivos: list[Motivo] = field(default_factory=list)

    @property
    def codigos(self) -> list[str]:
        return [m.codigo for m in self.motivos]


def _normalizar_rfc(rfc: str) -> str:
    return re.sub(r"[\s-]", "", rfc).upper()


def validar(factura: Factura, hoy: date | None = None) -> ResultadoValidacion:
    hoy = hoy or date.today()
    motivos: list[Motivo] = []

    faltantes = [c for c in CAMPOS_OBLIGATORIOS if getattr(factura, c) in (None, "")]
    if not factura.conceptos:
        faltantes.append("conceptos")
    if faltantes:
        motivos.append(Motivo("campo_faltante", "Faltan campos obligatorios: " + ", ".join(faltantes)))

    for campo, codigo, etiqueta in (
        ("rfc_emisor", "rfc_invalido", "RFC del emisor"),
        ("rfc_receptor", "rfc_receptor_invalido", "RFC del receptor"),
    ):
        valor = getattr(factura, campo)
        if valor and not PATRON_RFC.match(_normalizar_rfc(valor)):
            motivos.append(Motivo(codigo, f"El {etiqueta} '{valor}' no tiene un formato válido"))

    if factura.folio_fiscal and not PATRON_UUID.match(factura.folio_fiscal.strip()):
        motivos.append(Motivo(
            "folio_fiscal_invalido",
            f"El folio fiscal '{factura.folio_fiscal}' no tiene el formato de un UUID",
        ))

    if factura.fecha:
        try:
            fecha = date.fromisoformat(factura.fecha)
        except ValueError:
            motivos.append(Motivo("fecha_invalida", f"La fecha '{factura.fecha}' no es válida"))
        else:
            if fecha > hoy:
                motivos.append(Motivo("fecha_futura", f"La fecha {fecha.isoformat()} es posterior a hoy"))

    for k in factura.conceptos:
        if k.valor_unitario is not None:
            esperado = round(k.cantidad * k.valor_unitario, 2)
            if abs(esperado - k.importe) > TOLERANCIA_CONCEPTO:
                motivos.append(Motivo(
                    "concepto_importe_incoherente",
                    f"En '{k.descripcion[:40]}', cantidad por valor unitario ({esperado:.2f}) "
                    f"no coincide con el importe ({k.importe:.2f})",
                ))

    if factura.subtotal is not None and factura.conceptos:
        suma = round(sum(c.importe for c in factura.conceptos), 2)
        if abs(suma - factura.subtotal) > TOLERANCIA:
            motivos.append(Motivo(
                "subtotal_no_coincide_conceptos",
                f"La suma de los conceptos ({suma:.2f}) no coincide con el subtotal ({factura.subtotal:.2f})",
            ))

    descuento = round(sum((k.descuento or 0.0) for k in factura.conceptos), 2)
    iva = factura.iva or 0.0

    if factura.subtotal is not None:
        base = round(factura.subtotal - descuento, 2)

        iva_maximo = round(base * TASA_IVA, 2)
        if iva < -TOLERANCIA or iva > iva_maximo + TOLERANCIA:
            motivos.append(Motivo(
                "iva_incoherente",
                f"El IVA ({iva:.2f}) debe estar entre 0 y el 16 % de la base ({iva_maximo:.2f})",
            ))

        if factura.total is not None:
            total_esperado = round(base + iva, 2)
            if abs(total_esperado - factura.total) > TOLERANCIA:
                motivos.append(Motivo(
                    "total_no_coincide",
                    f"El total ({factura.total:.2f}) no coincide con subtotal menos descuento más IVA "
                    f"({total_esperado:.2f})",
                ))

    estado = "revision_manual" if motivos else "validado"
    return ResultadoValidacion(estado=estado, motivos=motivos)