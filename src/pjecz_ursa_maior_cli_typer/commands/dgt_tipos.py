"""
DGT Tipos commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_string
from pjecz_ursa_maior_cli_typer.models.dgt_tipos import DgtTipo

app = Typer(help="DGT Tipos comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    descripcion: str | None = None,
):
    """Consultar tipos"""
    console = Console()
    console.print("Consultando tipos...")

    # Preparar tabla
    tabla = Table(title="DGT Tipos")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción", header_style="green")

    # Cláusulas where
    where_clauses = [DgtTipo.estatus == "A"]
    if descripcion and (descripcion := safe_string(descripcion)):
        where_clauses.append(DgtTipo.descripcion.like("%" + descripcion + "%"))

    # Sentencia
    stmt = (
        select(
            DgtTipo.clave,
            DgtTipo.descripcion,
        )
        .select_from(DgtTipo)
        .where(*where_clauses)
        .order_by(DgtTipo.clave)
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
