"""
DGT Plataformas Autoridades, modelos
"""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pjecz_ursa_maior_cli_typer.utils.database import Base


class DgtPlataformaAutoridad(Base):
    """DgtPlataformaAutoridad"""

    # Nombre de la tabla
    __tablename__ = "dgt_plataformas_autoridades"

    # Clave primaria
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Claves foráneas
    # La autoridad es única: cada autoridad sólo puede tener una plataforma
    autoridad_id: Mapped[int] = mapped_column(ForeignKey("autoridades.id"), unique=True)
    autoridad: Mapped["Autoridad"] = relationship(back_populates="dgt_plataforma_autoridad")
    dgt_plataforma_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dgt_plataformas.id"), index=True)
    dgt_plataforma: Mapped["DgtPlataforma"] = relationship(back_populates="dgt_plataformas_autoridades")

    @classmethod
    def asignar(cls, autoridad_id: int, dgt_plataforma_id) -> tuple["DgtPlataformaAutoridad", bool]:
        """
        Asignar una autoridad a una plataforma

        Como la autoridad es única, se reutiliza su registro si ya existe:
        - Si está activo con la misma plataforma, no hace nada
        - Si está activo con otra plataforma, provoca ValueError
        - Si está eliminado, lo recupera con la plataforma indicada

        Entrega el registro y verdadero si hubo cambios
        """
        dgt_plataforma_autoridad = cls.query.filter_by(autoridad_id=autoridad_id).first()
        if dgt_plataforma_autoridad is None:
            dgt_plataforma_autoridad = cls(autoridad_id=autoridad_id, dgt_plataforma_id=dgt_plataforma_id)
            dgt_plataforma_autoridad.save()
            return dgt_plataforma_autoridad, True
        if dgt_plataforma_autoridad.estatus == "A":
            if str(dgt_plataforma_autoridad.dgt_plataforma_id) == str(dgt_plataforma_id):
                return dgt_plataforma_autoridad, False
            raise ValueError(f"Ya está asignada a la plataforma {dgt_plataforma_autoridad.dgt_plataforma.descripcion}")
        dgt_plataforma_autoridad.dgt_plataforma_id = dgt_plataforma_id
        dgt_plataforma_autoridad.estatus = "A"
        dgt_plataforma_autoridad.save()
        return dgt_plataforma_autoridad, True

    def __repr__(self):
        """Representación"""
        return f"<DgtPlataformaAutoridad {self.id}>"
