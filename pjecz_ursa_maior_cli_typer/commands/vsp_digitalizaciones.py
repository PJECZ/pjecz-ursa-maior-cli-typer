"""
VSP Digitalizaciones commandos
"""

import base64
import csv
import sys
from pathlib import Path
from uuid import UUID

from google.cloud import storage
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.vsp_digitalizaciones import VspDigitalizacion
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.digitalizaciones import es_uuid_valido
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="VSP Digitalizaciones comandos")


@app.command()
def consultar(
    autoridad_clave: str = "",
    offset: int = 0,
    limit: int = 40,
):
    """Consultar VspDigitalizacion"""
    console = Console()
    console.print("Consultando VspDigitalizacion...")
    db = get_database()
    stmt = (
        select(
            VspDigitalizacion.archivo_uuid,
            Autoridad.clave.label("autoridad_clave"),
            VspDigitalizacion.expediente,
            VspDigitalizacion.expediente_anio,
            VspDigitalizacion.expediente_num,
            VspDigitalizacion.descripcion,
        )
        .join(Autoridad)
    )
    autoridad_clave = safe_clave(autoridad_clave)
    if autoridad_clave != "":
        autoridad = db.execute(select(Autoridad.id).filter(Autoridad.clave == autoridad_clave)).first()
        if autoridad is None:
            console.print(f"[red]Autoridad con clave {autoridad_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(VspDigitalizacion.autoridad_id == autoridad.id)
    stmt = stmt.order_by(VspDigitalizacion.creado.desc()).offset(offset).limit(limit)
    tabla = Table(title="VSP Digitalizaciones")
    tabla.add_column("UUID", header_style="green", no_wrap=True)
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Expediente", header_style="green")
    tabla.add_column("Año", header_style="green")
    tabla.add_column("Número", header_style="green")
    tabla.add_column("Descripción", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(
            str(item.archivo_uuid),
            item.autoridad_clave,
            item.expediente,
            str(item.expediente_anio),
            str(item.expediente_num),
            item.descripcion,
        )
    console.print(tabla)
