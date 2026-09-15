"""
DGT Entregas commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_entregas import DgtEntrega
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="DGT Entregas comandos")


@app.command()
def consultar(
    autoridad_clave: str = "",
    dgt_ruta_clave: str = "",
    offset: int = 0,
    limit: int = 40,
):
    """Consultar DGT entregas"""
    console = Console()
    console.print("Consultando DGT entregas...")
    db = get_database()
    stmt = select(
        DgtEntrega.id,
        Autoridad.clave.label("autoridad_clave"),
        DgtRuta.clave.label("dgt_ruta_clave"),
        DgtEntrega.archivo_nombre,
        DgtEntrega.archivo_tamano,
        DgtEntrega.archivo_actualizado,
    ).join(Autoridad).join(DgtRuta)
    autoridad_clave = safe_clave(autoridad_clave)
    if autoridad_clave != "":
        autoridad = db.execute(select(Autoridad.id).filter(Autoridad.clave == autoridad_clave)).first()
        if autoridad is None:
            console.print(f"[red]Autoridad con clave {autoridad_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(DgtEntrega.autoridad_id == autoridad.id)
    dgt_ruta_clave = safe_clave(dgt_ruta_clave)
    if dgt_ruta_clave != "":
        dgt_ruta = db.execute(select(DgtRuta.id).filter(DgtRuta.clave == dgt_ruta_clave)).first()
        if dgt_ruta is None:
            console.print(f"[red]DGT ruta con clave {dgt_ruta_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(DgtEntrega.dgt_ruta_id == dgt_ruta.id)
    stmt = stmt.order_by(DgtEntrega.archivo_actualizado.desc()).offset(offset).limit(limit)
    tabla = Table(title="DGT Entregas")
    tabla.add_column("ID", header_style="green", no_wrap=True)
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Ruta", header_style="green", no_wrap=True)
    tabla.add_column("Archivo", header_style="green")
    tabla.add_column("Tamaño", header_style="green", justify="right")
    tabla.add_column("Actualizado", header_style="green", no_wrap=True)
    for item in db.execute(stmt):
        tabla.add_row(
            str(item.id),
            item.autoridad_clave,
            item.dgt_ruta_clave,
            item.archivo_nombre,
            str(item.archivo_tamano),
            str(item.archivo_actualizado),
        )
    console.print(tabla)
