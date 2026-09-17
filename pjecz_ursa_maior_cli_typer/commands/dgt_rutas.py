"""
DGT Rutas commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.models.dgt_tipos import DgtTipo
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="DGT Rutas comandos")


@app.command()
def consultar(
    dgt_deposito_clave: str = "",
    dgt_tipo_clave: str = "",
    autoridad_clave: str = "",
    offset: int = 0,
    limit: int = 40,
):
    """Consultar DGT rutas"""
    console = Console()
    console.print("Consultando DGT rutas...")
    db = get_database()
    stmt = select(DgtRuta.clave, DgtDeposito.clave.label("dgt_deposito_clave"), DgtRuta.autoridad_clave, DgtTipo.clave.label("dgt_tipo_clave"), DgtRuta.directorio).join(DgtTipo).join(DgtDeposito)
    dgt_deposito_clave = safe_clave(dgt_deposito_clave, max_len=64)
    if dgt_deposito_clave != "":
        dgt_deposito = db.execute(select(DgtDeposito.id).filter(DgtDeposito.clave == dgt_deposito_clave)).first()
        if dgt_deposito is None:
            console.print(f"[red]DGT depósito con clave {dgt_deposito_clave} no encontrado[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(DgtRuta.dgt_deposito_id == dgt_deposito.id)
    dgt_tipo_clave = safe_clave(dgt_tipo_clave, max_len=64)
    if dgt_tipo_clave != "":
        dgt_tipo = db.execute(select(DgtTipo.id).filter(DgtTipo.clave == dgt_tipo_clave)).first()
        if dgt_tipo is None:
            console.print(f"[red]DGT tipo con clave {dgt_tipo_clave} no encontrado[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(DgtRuta.dgt_tipo_id == dgt_tipo.id)
    autoridad_clave = safe_clave(autoridad_clave)
    if autoridad_clave != "":
        stmt = stmt.filter(DgtRuta.autoridad_clave == autoridad_clave)
    stmt = stmt.order_by(DgtRuta.clave).offset(offset).limit(limit)
    tabla = Table(title="DGT Rutas")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Depósito", header_style="green", no_wrap=True)
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Tipo", header_style="green", no_wrap=True)
    tabla.add_column("Directorio", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.dgt_deposito_clave, item.autoridad_clave, item.dgt_tipo_clave, item.directorio)
    console.print(tabla)
