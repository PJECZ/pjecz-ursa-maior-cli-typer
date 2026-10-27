"""
Distritos commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.models.distritos import Distrito

app = Typer(help="Distritos comandos")


@app.command()
def consultar():
    """Consultar distritos"""
    console = Console()
    console.print("Consultando distritos...")
    tabla = Table(title="Distritos")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Nombre corto", header_style="green")
    stmt = select(Distrito.clave, Distrito.nombre_corto).filter(Distrito.estatus == "A").order_by(Distrito.clave)
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(item.clave, item.nombre_corto)
    console.print(tabla)
