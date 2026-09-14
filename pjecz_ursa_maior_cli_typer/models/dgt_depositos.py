"""
DGT Depósitos modelos
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtDepositos(Base):
    """DgtDepositos: pjecz-cetus y pjecz-aquarius"""

    # Nombre de la tabla
    __tablename__ = "dgt_depositos"

    # Clave primaria
    id: Mapped[int] = mapped_column(primary_key=True)

    # Columnas
    clave: Mapped[str] = mapped_column(String(64), unique=True)
    descripcion: Mapped[str] = mapped_column(String(256))

    # Hijos
    dgt_rutas: Mapped[list["DgtRuta"]] = relationship(back_populates="dgt_deposito")

    def __repr__(self):
        """Representación"""
        return f"<DgtDepositos {self.id}>"
