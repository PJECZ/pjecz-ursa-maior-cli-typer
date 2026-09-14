"""
DGT Rutas modelos
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtRuta(Base):
    """DgtRuta"""

    # Nombre de la tabla
    __tablename__ = "dgt_rutas"

    # Clave primaria
    id: Mapped[int] = mapped_column(primary_key=True)

    # Clave foránea
    dgt_deposito_id: Mapped[int] = mapped_column(ForeignKey("dgt_depositos.id"))
    dgt_deposito: Mapped["DgtDepositos"] = relationship(back_populates="dgt_digitalizaciones")
    dgt_tipo_id: Mapped[int] = mapped_column(ForeignKey("dgt_tipos.id"))
    dgt_tipo: Mapped["DgtTipo"] = relationship(back_populates="dgt_entregas")

    # Columnas
    clave: Mapped[str] = mapped_column(String(16), unique=True)
    directorio: Mapped[str] = mapped_column(String(512))

    # Hijos
    dgt_digitalizaciones: Mapped[list["DgtDigitalizacion"]] = relationship(back_populates="dgt_ruta")
    dgt_entregas: Mapped[list["DgtEntrega"]] = relationship(back_populates="dgt_ruta")

    def __repr__(self):
        """Representación"""
        return f"<DgtRuta {self.id}>"
