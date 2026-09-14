"""
DGT Digitalizaciones commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones import DgtDigitalizacion
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="DGT Digitalizaciones comandos")


@app.command()
def consultar(autoridad_clave: str = "", offset: int = 0, limit: int = 40):
    """Consultar digitalizaciones"""
    console = Console()
    console.print("Consultando digitalizaciones...")
