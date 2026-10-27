import re
from dataclasses import dataclass, field
from datetime import date

from app.schemas import Factura

TASA_IVA = 0.16
TOLERANCIA = 0.02
PATRON_RFC = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
CAMPOS_OBLIGATORIOS = ["emisor", "rfc_emisor", "fecha", "subtotal", "iva", "total"]


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

    if factura.rfc_emisor and not PATRON_RFC.match(_normalizar_rfc(factura.rfc_emisor)):
        motivos.append(Motivo("rfc_invalido", f"El RFC '{factura.rfc_emisor}' no tiene un formato válido"))

    if factura.fecha:
        try:
            fecha = date.fromisoformat(factura.fecha)
        except ValueError:
            motivos.append(Motivo("fecha_invalida", f"La fecha '{factura.fecha}' no es válida"))
        else:
            if fecha > hoy:
                motivos.append(Motivo("fecha_futura", f"La fecha {fecha.isoformat()} es posterior a hoy"))

    if factura.subtotal is not None and factura.conceptos:
        suma = round(sum(c.importe for c in factura.conceptos), 2)
        if abs(suma - factura.subtotal) > TOLERANCIA:
            motivos.append(Motivo(
                "subtotal_no_coincide_conceptos",
                f"La suma de los conceptos ({suma:.2f}) no coincide con el subtotal ({factura.subtotal:.2f})",
            ))

    if factura.subtotal is not None and factura.iva is not None:
        iva_esperado = round(factura.subtotal * TASA_IVA, 2)
        if abs(iva_esperado - factura.iva) > TOLERANCIA:
            motivos.append(Motivo(
                "iva_incoherente",
                f"El IVA ({factura.iva:.2f}) no corresponde al 16 % del subtotal ({iva_esperado:.2f})",
            ))

    if None not in (factura.subtotal, factura.iva, factura.total):
        total_esperado = round(factura.subtotal + factura.iva, 2)
        if abs(total_esperado - factura.total) > TOLERANCIA:
            motivos.append(Motivo(
                "total_no_coincide",
                f"El total ({factura.total:.2f}) no coincide con subtotal más IVA ({total_esperado:.2f})",
            ))

    estado = "revision_manual" if motivos else "validado"
    return ResultadoValidacion(estado=estado, motivos=motivos)