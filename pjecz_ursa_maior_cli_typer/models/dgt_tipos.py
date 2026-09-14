"""
DGT Tipos modelos
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtTipo(Base):
    """DgtTipo"""

    # Nombre de la tabla
    __tablename__ = "dgt_tipos"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Columnas
    clave: Mapped[str] = mapped_column(String(16), unique=True)
    descripcion: Mapped[str] = mapped_column(String(256))

    # Hijos
    dgt_rutas: Mapped[list["DgtRuta"]] = relationship(back_populates="dgt_tipo")

    def __repr__(self):
        """Representación"""
        return f"<DgtTipo {self.id}>"
