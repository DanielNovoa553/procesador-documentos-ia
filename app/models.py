from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _ahora():
    return datetime.now(timezone.utc)


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archivo: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    estado: Mapped[str] = mapped_column(String(20), index=True)
    motivos: Mapped[list] = mapped_column(JSON, default=list)
    datos: Mapped[dict] = mapped_column(JSON)
    modelo: Mapped[str] = mapped_column(String(100))
    emisor: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    rfc_emisor: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    nombre_receptor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rfc_receptor: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    fecha: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, index=True, nullable=True)
    folio: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    folio_fiscal: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    conceptos: Mapped[list["ConceptoDocumento"]] = relationship(
        back_populates="documento",
        cascade="all, delete-orphan",
        order_by="ConceptoDocumento.posicion",
    )


class ConceptoDocumento(Base):
    __tablename__ = "conceptos_documento"
    __table_args__ = (
        Index("ix_conceptos_documento_documento_posicion", "documento_id", "posicion"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), index=True
    )
    posicion: Mapped[int] = mapped_column(Integer)
    descripcion: Mapped[str] = mapped_column(Text)
    cantidad: Mapped[float] = mapped_column(Float)
    importe: Mapped[float] = mapped_column(Float)
    clave_prod_serv: Mapped[str | None] = mapped_column(String(100), nullable=True)
    no_identificacion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clave_unidad: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unidad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valor_unitario: Mapped[float | None] = mapped_column(Float, nullable=True)
    descuento: Mapped[float | None] = mapped_column(Float, nullable=True)
    objeto_impuesto: Mapped[str | None] = mapped_column(String(100), nullable=True)
    documento: Mapped["Documento"] = relationship(back_populates="conceptos")


class BitacoraRevision(Base):
    __tablename__ = "bitacora_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), index=True
    )
    accion: Mapped[str] = mapped_column(String(20))
    revisor: Mapped[str] = mapped_column(String(100))
    comentario: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    estado_anterior: Mapped[str] = mapped_column(String(20))
    estado_nuevo: Mapped[str] = mapped_column(String(20))
    datos_anteriores: Mapped[dict] = mapped_column(JSON)
    datos_nuevos: Mapped[dict] = mapped_column(JSON)
    motivos_anteriores: Mapped[list] = mapped_column(JSON)
    motivos_nuevos: Mapped[list] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class ConfiguracionPersistida(Base):
    __tablename__ = "configuracion_app"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proveedor: Mapped[str] = mapped_column(String(20))
    modelo: Mapped[str] = mapped_column(String(100))
    privacidad: Mapped[str] = mapped_column(String(20))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)