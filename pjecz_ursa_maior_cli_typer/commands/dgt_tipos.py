"""
DGT Tipos commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.models.dgt_tipos import DgtTipo
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="DGT Tipos comandos")


@app.command()
def consultar(offset: int = 0, limit: int = 40):
    """Consultar DGT tipos"""
    console = Console()
    console.print("Consultando DGT tipos...")
    db = get_database()
    stmt = select(DgtTipo.clave, DgtTipo.descripcion).order_by(DgtTipo.clave).offset(offset).limit(limit)
    tabla = Table(title="DGT Tipos")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.descripcion)
    console.print(tabla)
