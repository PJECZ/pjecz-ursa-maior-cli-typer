"""
DGT Entregas Bitácoras modelos
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtEntregaBitacora(Base):
    """DgtEntregaBitacora"""

    EVENTOS = {
        "CREADO": "Creado",
        "ELIMINADO": "Eliminado",
        "MODIFICADO": "Modificado",
    }

    # Nombre de la tabla
    __tablename__ = "dgt_entregas_bitacoras"

    # Clave primaria
    id: Mapped[int] = mapped_column(primary_key=True)

    # Clave foránea
    dgt_entrega_id: Mapped[int] = mapped_column(ForeignKey("dgt_entregas.id"))
    dgt_entrega: Mapped["DgtEntrega"] = relationship(back_populates="dgt_entregas_bitacoras")

    # Columnas
    archivo_url: Mapped[str] = mapped_column(String(512))
    archivo_md5_old: Mapped[str] = mapped_column(String(32))
    archivo_md5_new: Mapped[str] = mapped_column(String(32))
    archivo_crc32c_old: Mapped[str] = mapped_column(String(8))
    archivo_crc32c_new: Mapped[str] = mapped_column(String(8))
    archivo_actualizado: Mapped[datetime]
    archivo_tamano: Mapped[int] = mapped_column(default=0)
    evento: Mapped[str] = mapped_column(Enum(*EVENTOS, name="dgt_entregas_bitacoras_eventos", native_enum=False))

    def __repr__(self):
        """Representación"""
        return f"<DgtEntregaBitacora {self.id}>"
