"""
VSP Digitalizaciones modelos
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class VspDigitalizacion(Base):
    """VspDigitalizacion"""

    # Nombre de la tabla
    __tablename__ = "vsp_digitalizaciones"

    # Clave primaria
    id: Mapped[int] = mapped_column(primary_key=True)

    # Clave foránea
    autoridad_id: Mapped[int] = mapped_column(ForeignKey("autoridades.id"))
    autoridad: Mapped["Autoridad"] = relationship(back_populates="vsp_digitalizaciones")

    # Columnas
    expediente: Mapped[str] = mapped_column(String(16))
    expediente_anio: Mapped[int]
    expediente_num: Mapped[int]
    descripcion: Mapped[Optional[str]] = mapped_column(String(256))
    observaciones: Mapped[Optional[str]] = mapped_column(String(1024))
    archivo_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    archivo: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(String(512))
    tamano: Mapped[Optional[int]]  # Bytes
    tiempo: Mapped[Optional[datetime]]  # Tiempo en el que fue subido a GCS
    enviado: Mapped[Optional[datetime]]  # Tiempo en el que fue enviado a SAJI, si es nulo aun no ha sido enviado

    def __repr__(self):
        """Representación"""
        return f"<VspDigitalizacion {self.id}>"
