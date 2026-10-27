"""
DGT Plataformas commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_string
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas import DgtPlataforma

app = Typer(help="DGT Plataformas comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    descripcion: str | None = None,
):
    """Consultar plataformas"""
    console = Console()
    console.print("Consultando plataformas...")

    # Preparar tabla
    tabla = Table(title="DGT Plataformas")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción", header_style="green")

    # Cláusulas where
    where_clauses = [DgtPlataforma.estatus == "A"]
    if descripcion and (descripcion := safe_string(descripcion)):
        where_clauses.append(DgtPlataforma.descripcion.like("%" + descripcion + "%"))

    # Sentencia
    stmt = (
        select(
            DgtPlataforma.clave,
            DgtPlataforma.descripcion,
        )
        .select_from(DgtPlataforma)
        .where(*where_clauses)
        .order_by(DgtPlataforma.clave)
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.clave,
                item.descripcion,
            )
    console.print(tabla)
