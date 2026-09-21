"""
DGT Depósitos commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="DGT Depósitos comandos")


@app.command()
def consultar(offset: int = 0, limit: int = 40):
    """Consultar DGT depósitos"""
    console = Console()
    console.print("Consultando DGT depósitos...")
    db = get_database()
    stmt = select(DgtDeposito.clave, DgtDeposito.descripcion, DgtDeposito.proposito).order_by(DgtDeposito.clave).offset(offset).limit(limit)
    tabla = Table(title="DGT Depósitos")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción", header_style="green")
    tabla.add_column("Propósito", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.descripcion, item.proposito)
    console.print(tabla)
