"""
DGT Plataformas Bitácoras, modelos
"""

import uuid
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtPlataformaBitacora(Base):
    """DgtPlataformaBitacora"""

    # Nombre de la tabla
    __tablename__ = "dgt_plataformas_bitacoras"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Claves foráneas
    dgt_plataforma_endpoint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dgt_plataformas_endpoints.id"))
    dgt_plataforma_endpoint: Mapped["DgtPlataformaEndpoint"] = relationship(back_populates="dgt_plataformas_bitacoras")

    # Columnas
    payload: Mapped[dict] = mapped_column(JSON, default={})
    respuesta_codigo: Mapped[int] = mapped_column(default=0)
    respuesta_exitosa: Mapped[bool] = mapped_column(default=False)
    respuesta_mensaje: Mapped[Optional[str]] = mapped_column(String(1024), default="")
    respuesta_datos: Mapped[dict] = mapped_column(JSON, default={})

    def __repr__(self):
        """Representación"""
        return f"<DgtPlataformaBitacora {self.id}>"
