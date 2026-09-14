"""
DGT Digitalizaciones Bitácoras modelos
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtDigitalizacionBitacora(Base):
    """DgtDigitalizacionBitacora"""

    EVENTOS = {
        "CREADO": "Creado",
        "ELIMINADO": "Eliminado",
        "MODIFICADO": "Modificado",
    }

    # Nombre de la tabla
    __tablename__ = "dgt_digitalizaciones_bitacoras"

    # Clave primaria
    id: Mapped[int] = mapped_column(primary_key=True)

    # Clave foránea
    dgt_digitalizacion_id: Mapped[int] = mapped_column(ForeignKey("dgt_digitalizaciones.id"))
    dgt_digitalizacion: Mapped["DgtDigitalizacion"] = relationship(back_populates="dgt_digitalizaciones_bitacoras")

    # Columnas
    archivo_url: Mapped[str] = mapped_column(String(512))
    archivo_md5_old: Mapped[str] = mapped_column(String(32))
    archivo_md5_new: Mapped[str] = mapped_column(String(32))
    archivo_crc32c_old: Mapped[str] = mapped_column(String(8))
    archivo_crc32c_new: Mapped[str] = mapped_column(String(8))
    archivo_actualizado: Mapped[datetime]
    archivo_tamano: Mapped[int] = mapped_column(default=0)
    evento: Mapped[str] = mapped_column(Enum(*EVENTOS, name="dgt_digitalizaciones_bitacoras_eventos", native_enum=False))

    def __repr__(self):
        """Representación"""
        return f"<DgtDigitalizacionBitacora {self.id}>"
