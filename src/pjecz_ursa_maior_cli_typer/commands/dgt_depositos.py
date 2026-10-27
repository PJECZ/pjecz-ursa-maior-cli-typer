"""
DGT Depósitos commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.exceptions import MyNotValidParamError
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_string
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito

app = Typer(help="DGT Depósitos comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    descripcion: str | None = None,
    proposito: str | None = None,
):
    """Consultar depósitos"""
    console = Console()
    console.print("Consultando depósitos...")

    # Preparar tabla
    tabla = Table(title="DGT Depósitos")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción", header_style="green")
    tabla.add_column("Propósito", header_style="green", no_wrap=True)

    # Cláusulas where
    where_clauses = [DgtDeposito.estatus == "A"]
    if descripcion and (descripcion := safe_string(descripcion)):
        where_clauses.append(DgtDeposito.descripcion.like("%" + descripcion + "%"))
    if proposito and (proposito := safe_string(proposito)):
        if proposito not in DgtDeposito.PROPOSITOS:
            raise MyNotValidParamError(f"Propósito inválido, debe ser uno de: {', '.join(DgtDeposito.PROPOSITOS)}")
        where_clauses.append(DgtDeposito.proposito == proposito)

    # Sentencia
    stmt = (
        select(
            DgtDeposito.clave,
            DgtDeposito.descripcion,
            DgtDeposito.proposito,
        )
        .select_from(DgtDeposito)
        .where(*where_clauses)
        .order_by(DgtDeposito.clave)
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.clave,
                item.descripcion,
                item.proposito,
            )
    console.print(tabla)
