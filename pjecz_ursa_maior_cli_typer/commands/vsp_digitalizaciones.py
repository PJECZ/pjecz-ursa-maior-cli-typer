"""
VSP Digitalizaciones commandos
"""

import csv
from datetime import datetime
from pathlib import Path

import pytz
from openpyxl import Workbook
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.config.settings import get_settings
from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.vsp_digitalizaciones import VspDigitalizacion
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="VSP Digitalizaciones comandos")

EXPORTS_DIR = "exports"  # Subdirectorio donde depositar los archivos CSV y XLSX


def _consultar_vsp_digitalizaciones(
    db,
    console: Console,
    autoridad_clave: str = "",
    offset: int = 0,
    limit: int = 0,
):
    """Consultar vsp_digitalizaciones"""
    stmt = (
        select(
            VspDigitalizacion.archivo_uuid,
            Autoridad.clave.label("autoridad_clave"),
            VspDigitalizacion.expediente,
            VspDigitalizacion.expediente_anio,
            VspDigitalizacion.expediente_num,
            VspDigitalizacion.descripcion,
            VspDigitalizacion.url,
        ).join(Autoridad)
    )
    autoridad_clave = safe_clave(autoridad_clave)
    if autoridad_clave != "":
        autoridad = db.execute(select(Autoridad.id).filter(Autoridad.clave == autoridad_clave)).first()
        if autoridad is None:
            console.print(f"[red]Autoridad con clave {autoridad_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(VspDigitalizacion.autoridad_id == autoridad.id)
    stmt = stmt.filter(VspDigitalizacion.estatus == "A")
    if limit > 0:
        stmt = stmt.offset(offset).limit(limit)
    stmt = stmt.order_by(
        Autoridad.clave,
        VspDigitalizacion.expediente_anio,
        VspDigitalizacion.expediente_num,
        VspDigitalizacion.descripcion,
    )
    return db.execute(stmt)


@app.command()
def consultar(
    autoridad_clave: str = "",
    offset: int = 0,
    limit: int = 100,
):
    """Consultar vsp_digitalizaciones"""
    console = Console()
    console.print("Consultando vsp_digitalizaciones...")
    db = get_database()
    tabla = Table(title="VSP Digitalizaciones")
    tabla.add_column("UUID", header_style="green", no_wrap=True)
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Expediente", header_style="green")
    tabla.add_column("Año", header_style="green")
    tabla.add_column("Número", header_style="green")
    tabla.add_column("Descripción", header_style="green")
    for item in _consultar_vsp_digitalizaciones(db, console, autoridad_clave, offset, limit):
        tabla.add_row(
            str(item.archivo_uuid),
            item.autoridad_clave,
            item.expediente,
            str(item.expediente_anio),
            str(item.expediente_num),
            item.descripcion,
        )
    console.print(tabla)


@app.command()
def exportar_csv(autoridad_clave: str = ""):
    """Exportar la tabla vsp_digitalizaciones a un archivo CSV"""
    console = Console()
    console.print("Exportando la tabla vsp_digitalizaciones a un archivo CSV...")
    db = get_database()
    config = get_settings()
    timezone = pytz.timezone(config.TZ)

    # Definir el nombre del archivo CSV con la fecha y hora actual
    ahora_str = datetime.now(tz=timezone).strftime("%Y-%m-%d-%H%M%S")
    ruta = Path(EXPORTS_DIR, f"vsp_digitalizaciones_{ahora_str}.csv")
    if ruta.exists():
        console.print(f"[red]ERROR: {ruta} ya existe, no voy a sobreescribirlo.")
        raise Exit(code=1)

    # Abrir el archivo CSV
    contador = 0
    with open(ruta, "w", encoding="utf8") as puntero:
        respaldo = csv.writer(puntero)
        respaldo.writerow(
            [
                "UUID",
                "AUTORIDAD_CLAVE",
                "EXPEDIENTE",
                "EXPEDIENTE_ANIO",
                "EXPEDIENTE_NUM",
                "DESCRIPCION",
                "URL",
            ]
        )
        # Agregar las filas al archivo CSV
        for item in _consultar_vsp_digitalizaciones(db, console, autoridad_clave):
            respaldo.writerow(
                [
                    item.archivo_uuid,
                    item.autoridad_clave,
                    item.expediente,
                    item.expediente_anio,
                    item.expediente_num,
                    item.descripcion,
                    item.url,
                ]
            )
            contador += 1

    # Mensaje final
    console.print(f"Se exportaron {contador} filas al archivo {ruta.name}")


@app.command()
def exportar_xlsx(autoridad_clave: str = ""):
    """Exportar la tabla vsp_digitalizaciones a un archivo XLSX"""
    console = Console()
    console.print("Exportando la tabla vsp_digitalizaciones a un archivo XLSX...")
    db = get_database()
    config = get_settings()
    timezone = pytz.timezone(config.TZ)

    # Iniciar el archivo XLSX
    libro = Workbook()
    hoja = libro.active
    if hoja is None:
        console.print("[red]ERROR: Al crear la hoja de Excel.")
        raise Exit(code=1)

    # Agregar la fila con las cabeceras de las columnas
    hoja.append(
        [
            "UUID",
            "Autoridad clave",
            "Expediente",
            "Año",
            "Número",
            "Descripción",
            "URL",
        ]
    )

    # Agregar las filas con los datos
    contador = 0
    for item in _consultar_vsp_digitalizaciones(db, console, autoridad_clave):
        hoja.append(
            [
                str(item.archivo_uuid),
                item.autoridad_clave,
                item.expediente,
                item.expediente_anio,
                item.expediente_num,
                item.descripcion,
                item.url,
            ]
        )
        contador += 1

    # Definir el nombre del archivo XLSX con la fecha y hora actual
    ahora_str = datetime.now(tz=timezone).strftime("%Y-%m-%d-%H%M%S")
    ruta = Path(EXPORTS_DIR, f"vsp_digitalizaciones_{ahora_str}.xlsx")

    # Guardar el archivo XLSX
    try:
        libro.save(str(ruta))
    except Exception as error:
        console.print(f"[red]ERROR: Al guardar la hoja de Excel {error}")
        raise Exit(code=1)

    # Mensaje final
    console.print(f"Se exportaron {contador} filas al archivo {ruta.name}")
