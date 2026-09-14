"""
DGT Rutas modelos
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtRuta(Base):
    """DgtRuta"""

    # Nombre de la tabla
    __tablename__ = "dgt_rutas"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Claves foráneas
    dgt_deposito_id: Mapped[int] = mapped_column(ForeignKey("dgt_depositos.id"))
    dgt_deposito: Mapped["DgtDepositos"] = relationship(back_populates="dgt_rutas")
    dgt_tipo_id: Mapped[int] = mapped_column(ForeignKey("dgt_tipos.id"))
    dgt_tipo: Mapped["DgtTipo"] = relationship(back_populates="dgt_rutas")

    # Columnas
    clave: Mapped[str] = mapped_column(String(16), unique=True)
    directorio: Mapped[str] = mapped_column(String(512))

    # Hijos
    dgt_digitalizaciones: Mapped[list["DgtDigitalizacion"]] = relationship(back_populates="dgt_ruta")
    dgt_entregas: Mapped[list["DgtEntrega"]] = relationship(back_populates="dgt_ruta")

    def __repr__(self):
        """Representación"""
        return f"<DgtRuta {self.id}>"
