"""
Database utilities
"""

from datetime import datetime
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.sql.functions import now
from sqlalchemy.types import CHAR

from pjecz_ursa_maior_cli_typer.config.settings import get_settings


class Base(DeclarativeBase):
    """Base de los modelos de la base de datos"""

    creado: Mapped[datetime] = mapped_column(default=now(), server_default=now())
    modificado: Mapped[datetime] = mapped_column(default=now(), onupdate=now(), server_default=now())
    estatus: Mapped[str] = mapped_column(CHAR, default="A")


@lru_cache
def get_database() -> Session:
    """Obtener la sesion de la base de datos"""
    settings = get_settings()
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local()
