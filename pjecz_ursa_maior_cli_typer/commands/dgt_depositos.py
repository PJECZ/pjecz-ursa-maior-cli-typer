"""
DGT Depósitos commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DGTDeposito
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="DGT Depósitos comandos")
