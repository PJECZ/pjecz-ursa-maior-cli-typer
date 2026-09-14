"""
DGT Digitalizaciones modelos
"""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtDigitalizacion(Base):
    """DgtDigitalizacion"""

    # Nombre de la tabla
    __tablename__ = "dgt_digitalizaciones"

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

    # Columnas en el depósito de entrega
    entrega_archivo: Mapped[str] = mapped_column(String(256))
    entrega_url: Mapped[str] = mapped_column(String(512))

    # Columnas en el depósito de uso
    archivo_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    archivo: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(String(512))

    def __repr__(self):
        """Representación"""
        return f"<DgtDigitalizacion {self.id}>"
