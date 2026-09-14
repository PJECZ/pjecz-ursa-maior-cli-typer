"""
DGT Entregas modelos
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtEntrega(Base):
    """DgtEntrega"""

    # Nombre de la tabla
    __tablename__ = "dgt_entregas"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Claves foráneas
    autoridad_id: Mapped[int] = mapped_column(ForeignKey("autoridades.id"))
    autoridad: Mapped["Autoridad"] = relationship(back_populates="dgt_entregas")
    dgt_ruta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dgt_rutas.id"))
    dgt_ruta: Mapped["DgtRuta"] = relationship(back_populates="dgt_entregas")

    # Columnas con datos del archivo en el depósito
    archivo_nombre: Mapped[str] = mapped_column(String(256))
    archivo_url: Mapped[str] = mapped_column(String(512))
    archivo_md5: Mapped[str] = mapped_column(String(32))
    archivo_crc32c: Mapped[str] = mapped_column(String(8))
    archivo_actualizado: Mapped[datetime]
    archivo_tamano: Mapped[int]

    # Columnas de control
    expediente: Mapped[Optional[str]] = mapped_column(String(16))
    expediente_anio: Mapped[Optional[int]]
    expediente_num: Mapped[Optional[int]]
    descripcion: Mapped[Optional[str]] = mapped_column(String(256))

    # Hijos
    dgt_entregas_bitacoras: Mapped[list["DgtEntregaBitacora"]] = relationship(back_populates="dgt_entrega")

    def __repr__(self):
        """Representación"""
        return f"<DgtEntrega {self.id}>"
