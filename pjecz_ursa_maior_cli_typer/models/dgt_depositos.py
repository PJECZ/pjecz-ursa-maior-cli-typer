"""
DGT Depósitos modelos
"""

import uuid

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtDeposito(Base):
    """DgtDeposito"""

    PROPOSITOS = {
        "ND": "ND",
        "ENTREGAS": "Entregas",
        "DIGITALIZACIONES": "Digitalizaciones",
        "RESPALDOS": "Respaldos",
    }

    # Nombre de la tabla
    __tablename__ = "dgt_depositos"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Columnas
    clave: Mapped[str] = mapped_column(String(64), unique=True)
    descripcion: Mapped[str] = mapped_column(String(256))
    proposito: Mapped[str] = mapped_column(Enum(*PROPOSITOS, name="dgt_depositos_propositos", native_enum=False), index=True)

    # Hijos
    dgt_rutas: Mapped[list["DgtRuta"]] = relationship(back_populates="dgt_deposito")

    def __repr__(self):
        """Representación"""
        return f"<DgtDeposito {self.id}>"
