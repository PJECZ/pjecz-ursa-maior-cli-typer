"""
DGT Tipos modelos
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtTipo(Base):
    """DgtTipo: Expediente, Exhorto, Amaparo, etc."""

    # Nombre de la tabla
    __tablename__ = "dgt_tipos"

    # Clave primaria
    id: Mapped[int] = mapped_column(primary_key=True)

    # Columnas
    clave: Mapped[str] = mapped_column(String(16), unique=True)
    descripcion: Mapped[str] = mapped_column(String(256))

    # Hijos
    dgt_rutas: Mapped[list["DgtRuta"]] = relationship(back_populates="dgt_tipo")

    def __repr__(self):
        """Representación"""
        return f"<DgtTipo {self.id}>"
