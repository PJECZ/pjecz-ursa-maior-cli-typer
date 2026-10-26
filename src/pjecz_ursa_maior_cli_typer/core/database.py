"""
Database

Uso en línea de comandos (Typer, scripts, workers):

    from pjecz_ursa_maior_cli_typer.core.database import session_scope

    with session_scope() as session:
        session.add(objeto)
        # commit automático al salir; rollback si hay excepción
"""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
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
def get_engine() -> Engine:
    """Crear el engine una sola vez por proceso"""
    settings = get_settings()
    return create_engine(
        settings.database_uri,
        pool_size=10,  # Conexiones permanentes en el pool
        max_overflow=20,  # Conexiones extra temporales
        pool_pre_ping=True,  # Verifica la conexión antes de usarla
        pool_recycle=1800,  # Recicla conexiones cada 30 minutos
        echo=False,  # True para ver el SQL en desarrollo
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Fábrica de sesiones ligada al engine"""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager transaccional: commit al salir, rollback si hay error"""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
