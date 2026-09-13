"""
Distritos commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.models.distritos import Distrito
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="Distritos comandos")


@app.command()
def consultar():
    """Consultar distritos"""
    console = Console()
    console.print("Consultando distritos...")
    db = get_database()
    stmt = select(Distrito.clave, Distrito.nombre_corto).filter(Distrito.estatus == "A").order_by(Distrito.clave)
    tabla = Table(title="Materias")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Nombre corto", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.nombre_corto)
    console.print(tabla)
