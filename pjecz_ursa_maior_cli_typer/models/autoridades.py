"""
Autoridades modelos
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class Autoridad(Base):
    """Autoridad"""

    # Nombre de la tabla
    __tablename__ = "autoridades"

    # Clave primaria
    id: Mapped[int] = mapped_column(primary_key=True)

    # Claves foráneas
    distrito_id: Mapped[int] = mapped_column(ForeignKey("distritos.id"))
    distrito: Mapped["Distrito"] = relationship(back_populates="autoridades")
    materia_id: Mapped[int] = mapped_column(ForeignKey("materias.id"))
    materia: Mapped["Materia"] = relationship(back_populates="autoridades")

    # Columnas
    clave: Mapped[str] = mapped_column(String(16), unique=True)
    descripcion: Mapped[str] = mapped_column(String(256))
    descripcion_corta: Mapped[str] = mapped_column(String(64))
    directorio_edictos: Mapped[str] = mapped_column(String(256))
    directorio_estrados: Mapped[str] = mapped_column(String(256))
    directorio_glosas: Mapped[str] = mapped_column(String(256))
    directorio_listas_de_acuerdos: Mapped[str] = mapped_column(String(256))
    directorio_sentencias: Mapped[str] = mapped_column(String(256))
    es_archivo_solicitante: Mapped[bool] = mapped_column(default=False)
    es_cemasc: Mapped[bool] = mapped_column(default=False)
    es_defensoria: Mapped[bool] = mapped_column(default=False)
    es_extinto: Mapped[bool] = mapped_column(default=False)
    es_jurisdiccional: Mapped[bool] = mapped_column(default=False)
    es_notaria: Mapped[bool] = mapped_column(default=False)
    es_organo_especializado: Mapped[bool] = mapped_column(default=False)
    es_revisor_escrituras: Mapped[bool] = mapped_column(default=False)
    es_vsp_digitalizaciones: Mapped[bool] = mapped_column(default=False)

    # Hijos
    dgt_digitalizaciones: Mapped[list["DgtDigitalizacion"]] = relationship(back_populates="autoridad")
    dgt_entregas: Mapped[list["DgtEntrega"]] = relationship(back_populates="autoridad")
    vsp_digitalizaciones: Mapped[list["VspDigitalizacion"]] = relationship(back_populates="autoridad")

    def __repr__(self):
        """Representación"""
        return f"<Autoridad {self.clave}>"
