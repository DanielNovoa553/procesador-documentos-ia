import json

import pytest

from app import privacidad as p

TEXTO = """RFC emisor:   ZZZA010101AB1        Folio fiscal:   0B32DE2D-2D03-4A4A-804C-9FDEF9E8A151
Nombre emisor:   COMERCIAL AURORA S.A. DE C.V.        Serie:   A
RFC receptor:   REMA900101AB1
Nombre receptor:   ANA PAULA REYES MONTERO
Código postal, fecha y hora de emisión:   03650 2023-08-20 21:42:11
NOMBRE   CARLOS EDUARDO PINEDA SALAZAR
Dirección: AV. DEMO 123, COL. CENTRO, CDMX
Tel.: 55 3144 4837
Contacto: ventas@ejemplo.com.mx
1.00   H87-Pieza   CONSULTA MEDICA   954.00
Subtotal   10,627.59      IVA   860.41      Total   11,488.00
"""

SENSIBLES = [
    "ZZZA010101AB1", "REMA900101AB1", "0B32DE2D-2D03-4A4A-804C-9FDEF9E8A151",
    "ANA PAULA", "CARLOS EDUARDO", "ventas@ejemplo.com.mx", "55 3144 4837", "AV. DEMO",
]
CONSERVADO = ["Subtotal   10,627.59", "11,488.00", "03650 2023-08-20 21:42:11", "CONSULTA MEDICA", "Serie:"]


def test_enmascara_lo_sensible_y_conserva_el_resto():
    texto, _ = p.enmascarar(TEXTO, terminos=[])
    for valor in SENSIBLES:
        assert valor not in texto
    for valor in CONSERVADO:
        assert valor in texto
    p.verificar_limpio(texto, terminos=[])


def test_mismo_valor_recibe_el_mismo_marcador():
    texto, _ = p.enmascarar("A: ZZZA010101AB1 y otra vez ZZZA010101AB1", terminos=[])
    assert texto.count("[RFC_1]") == 2 and "[RFC_2]" not in texto


def test_terminos_configurados_se_enmascaran():
    texto, _ = p.enmascarar("Cliente frecuente: PEDRO DEMO SA", terminos=["PEDRO DEMO"])
    assert "PEDRO DEMO" not in texto


def test_restaura_los_valores_reales():
    _, m = p.enmascarar(TEXTO, terminos=[])
    respuesta = json.dumps({"rfc_emisor": "[RFC_1]", "folio_fiscal": "[UUID_1]", "total": 11488.0})
    datos = json.loads(p.restaurar_json(respuesta, m))
    assert datos["rfc_emisor"] == "ZZZA010101AB1"
    assert datos["folio_fiscal"] == "0B32DE2D-2D03-4A4A-804C-9FDEF9E8A151"
    assert datos["total"] == 11488.0


def test_marcador_inventado_se_deja_igual():
    _, m = p.enmascarar(TEXTO, terminos=[])
    assert json.loads(p.restaurar_json('{"rfc_emisor": "[RFC_99]"}', m))["rfc_emisor"] == "[RFC_99]"


@pytest.mark.parametrize("malo", ["RFC REMA900101AB1", "mail a@b.com", "tel 5512345678", "PEDRO DEMO aquí"])
def test_si_queda_algo_sensible_falla(malo):
    with pytest.raises(ValueError):
        p.verificar_limpio(malo, terminos=["PEDRO DEMO"])


def test_limite_conocido_nombres_sin_etiqueta_no_se_enmascaran():
    texto, _ = p.enmascarar("DANIELA FERNANDEZ SOTO\nCONSULTA PSIQUIATRICA   1,200.00", terminos=[])
    assert "DANIELA FERNANDEZ SOTO" in texto and "CONSULTA PSIQUIATRICA" in texto