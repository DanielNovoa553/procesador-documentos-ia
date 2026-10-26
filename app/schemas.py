from pydantic import BaseModel, Field


class Concepto(BaseModel):
    descripcion: str = Field(description="Descripción del concepto tal como aparece")
    cantidad: float = Field(description="Cantidad de unidades")
    importe: float = Field(description="Importe de la línea, sin símbolo de moneda")


class Factura(BaseModel):
    emisor: str | None = Field(description="Nombre o razón social del emisor")
    rfc_emisor: str | None = Field(description="RFC del emisor, tal como aparece")
    fecha: str | None = Field(description="Fecha de la factura en formato AAAA-MM-DD")
    subtotal: float | None = Field(description="Subtotal impreso, sin símbolo de moneda")
    iva: float | None = Field(description="IVA impreso, sin símbolo de moneda")
    total: float | None = Field(description="Total impreso, sin símbolo de moneda")
    conceptos: list[Concepto] = Field(description="Líneas de la factura, en orden")