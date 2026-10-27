"""
DGT Plataformas Autoridades commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave
from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas import DgtPlataforma
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas_autoridades import DgtPlataformaAutoridad

app = Typer(help="DGT Plataformas Autoridades comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    autoridad_clave: str | None = None,
    dgt_plataforma_clave: str | None = None,
):
    """Consultar plataformas autoridades"""
    console = Console()
    console.print("Consultando plataformas autoridades...")

    # Preparar tabla
    tabla = Table(title="DGT Plataformas Autoridades")
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Plataforma", header_style="green", no_wrap=True)

    # Cláusulas where
    where_clauses = [DgtPlataformaAutoridad.estatus == "A"]
    if autoridad_clave and (autoridad_clave := safe_clave(autoridad_clave)):
        where_clauses.append(Autoridad.clave == autoridad_clave)
    if dgt_plataforma_clave and (dgt_plataforma_clave := safe_clave(dgt_plataforma_clave, max_len=64)):
        where_clauses.append(DgtPlataforma.clave == dgt_plataforma_clave)

    # Sentencia
    stmt = (
        select(
            Autoridad.clave.label("autoridad_clave"),
            DgtPlataforma.clave.label("dgt_plataforma_clave"),
        )
        .select_from(DgtPlataformaAutoridad)
        .join(Autoridad, DgtPlataformaAutoridad.autoridad_id == Autoridad.id)
        .join(DgtPlataforma, DgtPlataformaAutoridad.dgt_plataforma_id == DgtPlataforma.id)
        .where(*where_clauses)
        .order_by(Autoridad.clave, DgtPlataforma.clave)
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.autoridad_clave,
                item.dgt_plataforma_clave,
            )
    console.print(tabla)
