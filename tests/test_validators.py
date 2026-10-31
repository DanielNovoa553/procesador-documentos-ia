from datetime import date, timedelta

from app.schemas import nueva_factura, nuevo_concepto
from app.validators import validar


def factura_base(**cambios):
    datos = dict(
        emisor="Comercial Norte S.A. de C.V.",
        rfc_emisor="CNO010203AB1",
        fecha=(date.today() - timedelta(days=5)).isoformat(),
        subtotal=1000.0,
        iva=160.0,
        total=1160.0,
        conceptos=[nuevo_concepto(descripcion="Licencia", cantidad=1, importe=1000.0)],
    )
    datos.update(cambios)
    return nueva_factura(**datos)


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
    conceptos = [nuevo_concepto(descripcion="Licencia", cantidad=1, importe=800.0)]
    assert "subtotal_no_coincide_conceptos" in validar(factura_base(conceptos=conceptos)).codigos


def test_campo_faltante():
    assert "campo_faltante" in validar(factura_base(emisor=None)).codigos


def test_diferencia_de_centavos_se_tolera():
    assert validar(factura_base(total=1160.01)).estado == "validado"

def test_factura_sin_iva_queda_validada():
    assert validar(factura_base(iva=None, total=1000.0)).estado == "validado"


def test_sin_iva_pero_total_distinto_va_a_revision():
    assert "total_no_coincide" in validar(factura_base(iva=None, total=1160.0)).codigos


def test_honorarios_sin_objeto_de_impuesto():
    c = nuevo_concepto(
        descripcion="HONORARIOS", cantidad=1400.0, importe=1400.0,
        valor_unitario=1.0, objeto_impuesto="No objeto de impuesto",
    )
    f = factura_base(subtotal=1400.0, iva=None, total=1400.0, conceptos=[c])
    assert validar(f).estado == "validado"


def test_folio_fiscal_valido_e_invalido():
    uuid = "41F38E36-A5CB-4A0E-AEAC-D944605CCAF5"
    assert validar(factura_base(folio_fiscal=uuid)).estado == "validado"
    assert "folio_fiscal_invalido" in validar(factura_base(folio_fiscal="abc-123")).codigos


def test_rfc_receptor_invalido():
    assert "rfc_receptor_invalido" in validar(factura_base(rfc_receptor="XYZ")).codigos


def test_concepto_con_importe_incoherente():
    c = nuevo_concepto(descripcion="Licencia", cantidad=2, importe=1000.0, valor_unitario=300.0)
    assert "concepto_importe_incoherente" in validar(factura_base(conceptos=[c])).codigos


def test_descuento_se_resta_antes_del_iva():
    c = nuevo_concepto(descripcion="Licencia", cantidad=1, importe=1000.0, descuento=100.0)
    f = factura_base(conceptos=[c], subtotal=1000.0, iva=144.0, total=1044.0)
    assert validar(f).estado == "validado"

def test_iva_parcial_por_tasas_mixtas_es_valido():
    conceptos = [
        nuevo_concepto(descripcion="Libros", cantidad=1, importe=5250.03),
        nuevo_concepto(descripcion="Material", cantidad=1, importe=5377.56),
    ]
    f = factura_base(conceptos=conceptos, subtotal=10627.59, iva=860.41, total=11488.00)
    assert validar(f).estado == "validado"


def test_iva_mayor_al_16_por_ciento_va_a_revision():
    assert "iva_incoherente" in validar(factura_base(iva=400.0, total=1400.0)).codigos