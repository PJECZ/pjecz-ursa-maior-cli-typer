"""
DGT Rutas commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave, safe_string
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.models.dgt_tipos import DgtTipo

app = Typer(help="DGT Rutas comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    dgt_deposito_clave: str | None = None,
    dgt_tipo_clave: str | None = None,
    autoridad_clave: str | None = None,
):
    """Consultar rutas"""
    console = Console()
    console.print("Consultando rutas...")

    # Preparar tabla
    tabla = Table(title="DGT Rutas")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Depósito", header_style="green", no_wrap=True)
    tabla.add_column("Tipo", header_style="green", no_wrap=True)
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Directorio", header_style="green")

    # Cláusulas where
    where_clauses = [DgtRuta.estatus == "A"]
    if dgt_deposito_clave and (dgt_deposito_clave := safe_clave(dgt_deposito_clave, max_len=64)):
        where_clauses.append(DgtDeposito.clave == dgt_deposito_clave)
    if dgt_tipo_clave and (dgt_tipo_clave := safe_clave(dgt_tipo_clave, max_len=64)):
        where_clauses.append(DgtTipo.clave == dgt_tipo_clave)
    if autoridad_clave and (autoridad_clave := safe_string(autoridad_clave)):
        where_clauses.append(DgtRuta.autoridad_clave.like("%" + autoridad_clave + "%"))

    # Sentencia
    stmt = (
        select(
            DgtRuta.clave,
            DgtDeposito.clave.label("dgt_deposito_clave"),
            DgtTipo.clave.label("dgt_tipo_clave"),
            DgtRuta.autoridad_clave,
            DgtRuta.directorio,
        )
        .select_from(DgtRuta)
        .join(DgtDeposito, DgtRuta.dgt_deposito_id == DgtDeposito.id)
        .join(DgtTipo, DgtRuta.dgt_tipo_id == DgtTipo.id)
        .where(*where_clauses)
        .order_by(DgtRuta.clave)
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.clave,
                item.dgt_deposito_clave,
                item.dgt_tipo_clave,
                item.autoridad_clave,
                item.directorio,
            )
    console.print(tabla)
