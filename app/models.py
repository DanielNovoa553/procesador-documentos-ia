from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

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
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


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