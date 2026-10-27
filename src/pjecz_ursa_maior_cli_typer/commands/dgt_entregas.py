"""
DGT Entregas commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave
from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_entregas import DgtEntrega
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta

app = Typer(help="DGT Entregas comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    autoridad_clave: str | None = None,
    dgt_ruta_clave: str | None = None,
    es_anomalo: bool | None = None,
):
    """Consultar entregas"""
    console = Console()
    console.print("Consultando entregas...")

    # Preparar tabla
    tabla = Table(title="DGT Entregas")
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Ruta", header_style="green", no_wrap=True)
    tabla.add_column("Archivo", header_style="green")
    tabla.add_column("Actualizado", header_style="green", no_wrap=True)
    tabla.add_column("Tamaño", header_style="green", no_wrap=True, justify="right")
    tabla.add_column("Último evento", header_style="green", no_wrap=True)
    tabla.add_column("Es anómalo", header_style="green", no_wrap=True)

    # Cláusulas where
    where_clauses = [DgtEntrega.estatus == "A"]
    if autoridad_clave and (autoridad_clave := safe_clave(autoridad_clave)):
        where_clauses.append(Autoridad.clave == autoridad_clave)
    if dgt_ruta_clave and (dgt_ruta_clave := safe_clave(dgt_ruta_clave, max_len=64)):
        where_clauses.append(DgtRuta.clave == dgt_ruta_clave)
    if es_anomalo is not None:
        where_clauses.append(DgtEntrega.es_anomalo == es_anomalo)

    # Sentencia
    stmt = (
        select(
            Autoridad.clave.label("autoridad_clave"),
            DgtRuta.clave.label("dgt_ruta_clave"),
            DgtEntrega.archivo_nombre,
            DgtEntrega.archivo_actualizado,
            DgtEntrega.archivo_tamano,
            DgtEntrega.ultimo_evento,
            DgtEntrega.es_anomalo,
        )
        .select_from(DgtEntrega)
        .join(Autoridad, DgtEntrega.autoridad_id == Autoridad.id)
        .join(DgtRuta, DgtEntrega.dgt_ruta_id == DgtRuta.id)
        .where(*where_clauses)
        .order_by(DgtEntrega.archivo_actualizado.desc())
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.archivo_actualizado.strftime("%Y-%m-%d %H:%M:%S"),
                item.autoridad_clave,
                item.dgt_ruta_clave,
                item.archivo_nombre,
                str(item.archivo_tamano),
                item.ultimo_evento,
                "Sí" if item.es_anomalo else "No",
            )
    console.print(tabla)
