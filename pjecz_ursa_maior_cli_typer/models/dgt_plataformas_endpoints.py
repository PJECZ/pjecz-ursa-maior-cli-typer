"""
DGT Plataformas Endpoints, modelos
"""

import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtPlataformaEndpoint(Base):
    """DgtPlataformaEndpoint"""

    PROPOSITOS = {
        "INSERTAR": "Insertar",
        "MODIFICAR": "Modificar",
        "ELIMINAR": "Eliminar",
    }

    METODOS = {
        "GET": "GET",
        "POST": "POST",
    }

    # Nombre de la tabla
    __tablename__ = "dgt_plataformas_endpoints"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Claves foráneas
    dgt_plataforma_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dgt_plataformas.id"))
    dgt_plataforma: Mapped["DgtPlataforma"] = relationship(back_populates="dgt_plataformas_endpoints")

    # Columnas
    descripcion: Mapped[str] = mapped_column(String(256))
    ruta: Mapped[str] = mapped_column(String(512))
    proposito: Mapped[str] = mapped_column(
        Enum(*PROPOSITOS, name="dgt_plataformas_endpoints_propositos", native_enum=False),
        index=True,
    )
    metodo: Mapped[str] = mapped_column(Enum(*METODOS, name="dgt_plataformas_endpoints_metodos", native_enum=False))
    payload_muestra: Mapped[dict] = mapped_column(JSON, default={})

    # Hijos
    dgt_plataformas_bitacoras: Mapped[list["DgtPlataformaBitacora"]] = relationship(back_populates="dgt_plataforma_endpoint")

    def __repr__(self):
        """Representación"""
        return f"<DgtPlataformaEndpoint {self.id}>"
