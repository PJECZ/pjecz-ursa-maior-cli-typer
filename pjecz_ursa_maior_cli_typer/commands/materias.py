"""
Materias commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.models.materias import Materia
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="Materias comandos")


@app.command()
def consultar():
    """Consultar materias"""
    console = Console()
    console.print("Consultando materias...")
    db = get_database()
    stmt = select(Materia.clave, Materia.nombre).filter(Materia.estatus == "A").order_by(Materia.clave)
    tabla = Table(title="Materias")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Nombre", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.nombre)
    console.print(tabla)
