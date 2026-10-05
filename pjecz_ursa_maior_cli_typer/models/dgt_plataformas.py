"""
DGT Plataformas, modelos
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtPlataforma(Base):
    """DgtPlataforma"""

    # Nombre de la tabla
    __tablename__ = "dgt_plataformas"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Columnas
    descripcion: Mapped[str] = mapped_column(String(256), unique=True)

    # Columnas que NO deben ser expuestas
    api_key: Mapped[str] = mapped_column(String(128))

    # Hijos
    dgt_plataformas_autoridades: Mapped[list["DgtPlataformaAutoridad"]] = relationship(back_populates="dgt_plataforma")
    dgt_plataformas_endpoints: Mapped[list["DgtPlataformaEndpoint"]] = relationship(back_populates="dgt_plataforma")

    @property
    def api_key_oculta(self):
        """API key oculta, solo muestra los primeros cuatro caracteres"""
        if not self.api_key:
            return ""
        return self.api_key[:4] + "*" * 12

    def __repr__(self):
        """Representación"""
        return f"<DgtPlataforma {self.id}>"
