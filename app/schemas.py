import json

from pydantic import BaseModel, Field

CAMPOS_NUEVOS_FACTURA = [
    "folio_fiscal", "serie", "folio", "lugar_expedicion", "tipo_comprobante",
    "exportacion", "moneda", "forma_pago", "metodo_pago",
    "regimen_fiscal_emisor", "nombre_receptor", "rfc_receptor",
    "codigo_postal_receptor", "regimen_fiscal_receptor", "uso_cfdi",
]
CAMPOS_NUEVOS_CONCEPTO = [
    "clave_prod_serv", "no_identificacion", "clave_unidad", "unidad",
    "valor_unitario", "descuento", "objeto_impuesto",
]


class Concepto(BaseModel):
    descripcion: str = Field(description="Descripción del concepto tal como aparece")
    cantidad: float = Field(description="Cantidad de unidades")
    importe: float = Field(description="Importe de la línea, sin símbolo de moneda")
    clave_prod_serv: str | None = Field(description="Clave del producto y/o servicio (código numérico)")
    no_identificacion: str | None = Field(description="Número de identificación del concepto")
    clave_unidad: str | None = Field(description="Clave de unidad, por ejemplo E48 o H87")
    unidad: str | None = Field(description="Nombre de la unidad, tal como aparece")
    valor_unitario: float | None = Field(description="Valor unitario, sin símbolo de moneda")
    descuento: float | None = Field(description="Descuento del concepto, sin símbolo de moneda")
    objeto_impuesto: str | None = Field(description="Objeto de impuesto, tal como aparece")


class Factura(BaseModel):
    emisor: str | None = Field(description="Nombre o razón social del emisor")
    rfc_emisor: str | None = Field(description="RFC del emisor, tal como aparece")
    fecha: str | None = Field(description="Fecha de emisión en formato AAAA-MM-DD, sin la hora")
    subtotal: float | None = Field(description="Subtotal impreso, sin símbolo de moneda")
    iva: float | None = Field(description="IVA impreso, sin símbolo de moneda")
    total: float | None = Field(description="Total impreso, sin símbolo de moneda")
    conceptos: list[Concepto] = Field(description="Líneas de la factura, en orden")

    folio_fiscal: str | None = Field(description="Folio fiscal (UUID de 36 caracteres)")
    serie: str | None = Field(description="Serie de la factura")
    folio: str | None = Field(description="Folio consecutivo del emisor")
    lugar_expedicion: str | None = Field(description="Código postal del lugar de expedición")
    tipo_comprobante: str | None = Field(description="Efecto o tipo de comprobante, tal como aparece")
    exportacion: str | None = Field(description="Campo exportación, tal como aparece")
    moneda: str | None = Field(description="Moneda, tal como aparece")
    forma_pago: str | None = Field(description="Forma de pago, tal como aparece")
    metodo_pago: str | None = Field(description="Método de pago, tal como aparece")
    regimen_fiscal_emisor: str | None = Field(description="Régimen fiscal del emisor")
    nombre_receptor: str | None = Field(description="Nombre o razón social del receptor")
    rfc_receptor: str | None = Field(description="RFC del receptor, tal como aparece")
    codigo_postal_receptor: str | None = Field(description="Código postal del receptor")
    regimen_fiscal_receptor: str | None = Field(description="Régimen fiscal del receptor")
    uso_cfdi: str | None = Field(description="Uso de CFDI, tal como aparece")


def _completar(datos: dict) -> dict:
    for campo in CAMPOS_NUEVOS_FACTURA:
        datos.setdefault(campo, None)
    for concepto in datos.get("conceptos") or []:
        if isinstance(concepto, dict):
            for campo in CAMPOS_NUEVOS_CONCEPTO:
                concepto.setdefault(campo, None)
    return datos


def factura_desde_json(texto: str) -> Factura:
    return Factura.model_validate(_completar(json.loads(texto)))


def nuevo_concepto(**datos) -> Concepto:
    for campo in CAMPOS_NUEVOS_CONCEPTO:
        datos.setdefault(campo, None)
    return Concepto(**datos)


def nueva_factura(**datos) -> Factura:
    for campo in CAMPOS_NUEVOS_FACTURA:
        datos.setdefault(campo, None)
    return Factura(**datos)