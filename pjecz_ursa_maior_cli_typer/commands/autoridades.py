"""
Autoridades commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="Autoridades comandos")


@app.command()
def consultar():
    """Consultar autoridades"""
    console = Console()
    console.print("Consultando autoridades...")
    db = get_database()
    stmt = select(Autoridad.clave, Autoridad.descripcion_corta).filter(Autoridad.estatus == "A").order_by(Autoridad.clave)
    tabla = Table(title="Materias")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción corta", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.descripcion_corta)
    console.print(tabla)
