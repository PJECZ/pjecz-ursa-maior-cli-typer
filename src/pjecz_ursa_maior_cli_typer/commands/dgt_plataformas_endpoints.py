"""
DGT Plataformas Endpoints commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave, safe_string
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas import DgtPlataforma
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas_endpoints import DgtPlataformaEndpoint

app = Typer(help="DGT Plataformas Endpoints comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    dgt_plataforma_clave: str | None = None,
    descripcion: str | None = None,
    proposito: str | None = None,
):
    """Consultar plataformas endpoints"""
    console = Console()
    console.print("Consultando plataformas endpoints...")

    # Preparar tabla
    tabla = Table(title="DGT Plataformas Endpoints")
    tabla.add_column("Plataforma", header_style="green", no_wrap=True)
    tabla.add_column("Descripción", header_style="green")
    tabla.add_column("Ruta", header_style="green")
    tabla.add_column("Propósito", header_style="green", no_wrap=True)
    tabla.add_column("Método", header_style="green", no_wrap=True)

    # Cláusulas where
    where_clauses = [DgtPlataformaEndpoint.estatus == "A"]
    if dgt_plataforma_clave and (dgt_plataforma_clave := safe_clave(dgt_plataforma_clave, max_len=64)):
        where_clauses.append(DgtPlataforma.clave == dgt_plataforma_clave)
    if descripcion and (descripcion := safe_string(descripcion)):
        where_clauses.append(DgtPlataformaEndpoint.descripcion.like("%" + descripcion + "%"))
    if proposito and (proposito := safe_string(proposito)):
        where_clauses.append(DgtPlataformaEndpoint.proposito == proposito)

    # Sentencia
    stmt = (
        select(
            DgtPlataforma.clave.label("dgt_plataforma_clave"),
            DgtPlataformaEndpoint.descripcion,
            DgtPlataformaEndpoint.ruta,
            DgtPlataformaEndpoint.proposito,
            DgtPlataformaEndpoint.metodo,
        )
        .select_from(DgtPlataformaEndpoint)
        .join(DgtPlataforma, DgtPlataformaEndpoint.dgt_plataforma_id == DgtPlataforma.id)
        .where(*where_clauses)
        .order_by(DgtPlataforma.clave, DgtPlataformaEndpoint.descripcion)
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.dgt_plataforma_clave,
                item.descripcion,
                item.ruta,
                item.proposito,
                item.metodo,
            )
    console.print(tabla)
