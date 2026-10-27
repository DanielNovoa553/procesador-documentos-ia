from datetime import date, timedelta

from app.schemas import Concepto, Factura
from app.validators import validar


def factura_base(**cambios) -> Factura:
    datos = dict(
        emisor="Comercial Norte S.A. de C.V.",
        rfc_emisor="CNO010203AB1",
        fecha=(date.today() - timedelta(days=5)).isoformat(),
        subtotal=1000.0,
        iva=160.0,
        total=1160.0,
        conceptos=[Concepto(descripcion="Licencia", cantidad=1, importe=1000.0)],
    )
    datos.update(cambios)
    return Factura(**datos)


def test_factura_correcta_queda_validada():
    resultado = validar(factura_base())
    assert resultado.estado == "validado"
    assert resultado.motivos == []


def test_total_incorrecto():
    resultado = validar(factura_base(total=1300.0))
    assert resultado.estado == "revision_manual"
    assert "total_no_coincide" in resultado.codigos


def test_rfc_invalido():
    assert "rfc_invalido" in validar(factura_base(rfc_emisor="CNO010203")).codigos


def test_fecha_futura():
    futura = (date.today() + timedelta(days=30)).isoformat()
    assert "fecha_futura" in validar(factura_base(fecha=futura)).codigos


def test_conceptos_no_suman_el_subtotal():
    conceptos = [Concepto(descripcion="Licencia", cantidad=1, importe=800.0)]
    assert "subtotal_no_coincide_conceptos" in validar(factura_base(conceptos=conceptos)).codigos


def test_campo_faltante():
    assert "campo_faltante" in validar(factura_base(emisor=None)).codigos


def test_diferencia_de_centavos_se_tolera():
    assert validar(factura_base(total=1160.01)).estado == "validado"