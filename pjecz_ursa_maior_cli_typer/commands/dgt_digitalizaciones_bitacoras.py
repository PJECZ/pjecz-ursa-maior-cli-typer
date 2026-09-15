"""
DGT Digitalizaciones Bitácoras commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones_bitacoras import DgtDigitalizacionBitacora
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = Typer(help="DGT Digitalizaciones Bitácoras comandos")
