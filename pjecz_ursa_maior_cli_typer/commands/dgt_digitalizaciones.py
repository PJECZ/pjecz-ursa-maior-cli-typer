"""
DGT Digitalizaciones commandos
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
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones import DgtDigitalizacion
from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones_bitacoras import DgtDigitalizacionBitacora
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.digitalizaciones import es_uuid_valido
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="DGT Digitalizaciones comandos")

DGT_DEPOSITO_PROPOSITO = "DIGITALIZACIONES"
VSP_DIGITALIZACIONES_CSV = "exports/vsp_digitalizaciones.csv"

@app.command()
def consultar(
    autoridad_clave: str = "",
    dgt_ruta_clave: str = "",
    offset: int = 0,
    limit: int = 40,
):
    """Consultar DgtDigitalizacion"""
    console = Console()
    console.print("Consultando DgtDigitalizacion...")
    db = get_database()
    stmt = (
        select(
            DgtDigitalizacion.id,
            Autoridad.clave.label("autoridad_clave"),
            DgtRuta.clave.label("dgt_ruta_clave"),
            DgtDigitalizacion.archivo_nombre,
            DgtDigitalizacion.archivo_tamano,
            DgtDigitalizacion.archivo_actualizado,
        )
        .join(Autoridad)
        .join(DgtRuta)
    )
    autoridad_clave = safe_clave(autoridad_clave)
    if autoridad_clave != "":
        autoridad = db.execute(select(Autoridad.id).filter(Autoridad.clave == autoridad_clave)).first()
        if autoridad is None:
            console.print(f"[red]Autoridad con clave {autoridad_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(DgtDigitalizacion.autoridad_id == autoridad.id)
    dgt_ruta_clave = safe_clave(dgt_ruta_clave)
    if dgt_ruta_clave != "":
        dgt_ruta = db.execute(select(DgtRuta.id).filter(DgtRuta.clave == dgt_ruta_clave)).first()
        if dgt_ruta is None:
            console.print(f"[red]DGT ruta con clave {dgt_ruta_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id)
    stmt = stmt.order_by(DgtDigitalizacion.archivo_actualizado.desc()).offset(offset).limit(limit)
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


def _obtener_dgt_ruta(
    db,
    console: Console,
    cliente: storage.Client,
    dgt_ruta: DgtRuta,
    dgt_deposito: DgtDeposito,
    autoridad: Autoridad,
):
    """Rastrear el depósito e insertar o actualizar registros en DgtDigitalizaciones de una ruta"""
    console.print(f"Depósito: {dgt_deposito.clave.lower()}, Directorio: {dgt_ruta.directorio}, Autoridad: {autoridad.clave}")

    # Leer el archivo CSV
    ruta = Path(VSP_DIGITALIZACIONES_CSV)
    if not ruta.exists():
        console.print(f"[red]ERROR: {ruta.name} no se encontró.")
        sys.exit(1)
    if not ruta.is_file():
        console.print(f"[red]ERROR: {ruta.name} no es un archivo.")
        sys.exit(1)
    vsp_digitalizaciones_registros = []
    with open(ruta, encoding="utf8") as puntero:
        rows = csv.DictReader(puntero)
        for row in rows:
            vsp_digitalizaciones_registros.append({
                "uuid": row["UUID"],
                "autoridad_clave": row["AUTORIDAD_CLAVE"],
                "expediente": row["EXPEDIENTE"],
                "expediente_anio": row["EXPEDIENTE_ANIO"],
                "expediente_num": row["EXPEDIENTE_NUM"],
                "descripcion": row["DESCRIPCION"],
                "url": row["URL"],
            })
    vsp_digitalizaciones_indice = {reg["uuid"]: reg for reg in vsp_digitalizaciones_registros}

    # Obtener los recursos en el depósito, en el directorio
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)

    # Inicializar variables
    archivo_urls_en_deposito = set()
    creados = modificados = omitidos = eliminados = invalidos = polizones = 0

    # Bucle por cada recurso en el depósito
    for blob in blobs:
        if blob.name.endswith("/"):
            continue

        # Obtener información del recurso
        archivo_url = f"gs://{dgt_deposito.clave.lower()}/{blob.name}"
        archivo_urls_en_deposito.add(archivo_url)
        archivo_nombre = blob.name.rsplit("/", maxsplit=1)[-1]
        archivo_md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
        archivo_crc32c = base64.b64decode(blob.crc32c).hex() if blob.crc32c else ""
        archivo_actualizado = blob.updated
        archivo_tamano = blob.size or 0

        # Obtener el UUID a partir del nombre
        uuid_str = archivo_nombre.rsplit(".", maxsplit=1)[0]
        if es_uuid_valido(uuid_str) is False:
            # Se encontró un archivo con UUID inválido
            invalidos += 1
            continue

        # Consultar en la base de datos si ya se tiene ese UUID
        consulta = (
            select(DgtDigitalizacion)
            .filter(DgtDigitalizacion.id == UUID(uuid_str))
        )
        dgt_digitalizacion = db.execute(consulta).scalar_one_or_none()

        # A) No existe una coincidencia
        if dgt_digitalizacion is None:
            # Buscar en el CSV
            datos = vsp_digitalizaciones_indice.get(uuid_str)
            if datos:
                # Insertar un nuevo DgtDigitalizacion
                dgt_digitalizacion = DgtDigitalizacion(
                    autoridad_id = autoridad.id,
                    dgt_ruta_id=dgt_ruta.id,
                    archivo_nombre=archivo_nombre,
                    archivo_url=archivo_url,
                    archivo_md5=archivo_md5,
                    archivo_crc32c=archivo_crc32c,
                    archivo_actualizado=archivo_actualizado,
                    archivo_tamano=archivo_tamano,
                    expediente=datos["expediente"],
                    expediente_anio=datos["expediente_anio"],
                    expediente_num=datos["expediente_num"],
                    descripcion=datos["descripcion"],
                )
                db.add(dgt_digitalizacion)
                db.flush()
                db.add(
                    DgtDigitalizacionBitacora(
                        dgt_digitalizacion_id=dgt_digitalizacion.id,
                        archivo_url=archivo_url,
                        archivo_md5_old="",
                        archivo_md5_new=archivo_md5,
                        archivo_crc32c_old="",
                        archivo_crc32c_new=archivo_crc32c,
                        archivo_actualizado=archivo_actualizado,
                        archivo_tamano=archivo_tamano,
                        evento="CREADO",
                    )
                )
                creados += 1
                continue
            else:
                # Se tiene un archivo que SÍ está en la base de datos pero NO se encuentra en el CSV
                polizones += 1
                continue

        # B) Ya existe y coincide el md5 y crc32c, omitir
        if dgt_digitalizacion.archivo_md5 == archivo_md5 and dgt_digitalizacion.archivo_crc32c == archivo_crc32c:
            omitidos += 1
            continue

        # C) Hay diferencias, actualizar y agregar bitácora de MODIFICADO
        archivo_md5_old = dgt_digitalizacion.archivo_md5
        archivo_crc32c_old = dgt_digitalizacion.archivo_crc32c
        dgt_digitalizacion.archivo_md5 = archivo_md5
        dgt_digitalizacion.archivo_crc32c = archivo_crc32c
        dgt_digitalizacion.archivo_actualizado = archivo_actualizado
        dgt_digitalizacion.archivo_tamano = archivo_tamano
        db.add(dgt_digitalizacion)
        db.add(
            DgtDigitalizacionBitacora(
                dgt_digitalizacion_id=dgt_digitalizacion.id,
                archivo_url=archivo_url,
                archivo_md5_old=archivo_md5_old,
                archivo_md5_new=archivo_md5,
                archivo_crc32c_old=archivo_crc32c_old,
                archivo_crc32c_new=archivo_crc32c,
                archivo_actualizado=archivo_actualizado,
                archivo_tamano=archivo_tamano,
                evento="MODIFICADO",
            )
        )
        modificados += 1

    # D) No están en el depósito, dar de baja y agregar bitácora de ELIMINADO
    eliminados = 0
    dgt_digitalizaciones_previas = db.execute(
        select(DgtDigitalizacion).filter(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id).filter(DgtDigitalizacion.estatus == "A")
    ).scalars()
    for dgt_digitalizacion in dgt_digitalizaciones_previas:
        if dgt_digitalizacion.archivo_url in archivo_urls_en_deposito:
            continue
        dgt_digitalizacion.estatus = "B"
        db.add(dgt_digitalizacion)
        db.add(
            DgtDigitalizacionBitacora(
                dgt_digitalizacion_id=dgt_digitalizacion.id,
                archivo_url=dgt_digitalizacion.archivo_url,
                archivo_md5_old=dgt_digitalizacion.archivo_md5,
                archivo_md5_new="",
                archivo_crc32c_old=dgt_digitalizacion.archivo_crc32c,
                archivo_crc32c_new="",
                archivo_actualizado=dgt_digitalizacion.archivo_actualizado,
                archivo_tamano=dgt_digitalizacion.archivo_tamano,
                evento="ELIMINADO",
            )
        )
        eliminados += 1

    db.commit()

    if creados > 0:
        console.print(f"Creados: [green]{creados}[/green]")
    if modificados > 0:
        console.print(f"Modificados: [yellow]{modificados}[/yellow]")
    if omitidos > 0:
        console.print(f"Omitidos: [gray]{omitidos}[/gray]")
    if eliminados > 0:
        console.print(f"Eliminados: [red]{eliminados}[/red]")
    if invalidos > 0:
        console.print(f"Archivos cuyo nombre no es un UUID: [red]{invalidos}[/red]")
    if polizones > 0:
        console.print(f"Archivos que NO están en el CSV: [red]{polizones}[/red]")


@app.command()
def obtener(dgt_ruta_clave: str = ""):
    """Insertar o actualizar registros en DgtDigitalizacion rastreando el depósito

    Si no se indica la clave de la DgtRuta, se procesan todas las DgtRutas con propósito ENTREGAS y estatus "A".
    """
    console = Console()
    db = get_database()

    consulta = (
        select(DgtRuta, DgtDeposito, Autoridad)
        .join(DgtDeposito)
        .join(Autoridad, Autoridad.clave == DgtRuta.autoridad_clave)
        .where(DgtDeposito.proposito == DGT_DEPOSITO_PROPOSITO)
    )

    dgt_ruta_clave = safe_clave(dgt_ruta_clave, max_len=64)
    if dgt_ruta_clave != "":
        console.print(f"Obteniendo DgtEntregas de {dgt_ruta_clave}...")
        consulta = consulta.where(DgtRuta.clave == dgt_ruta_clave).where(DgtRuta.estatus == "A")
        renglones = db.execute(consulta).all()
        if not renglones:
            console.print(f"[red]DgtRuta con clave {dgt_ruta_clave} no encontrada o eliminada[/red]")
            raise Exit(code=1)
    else:
        console.print("Obteniendo DgtEntregas de todas las rutas activas...")
        consulta = consulta.where(DgtRuta.estatus == "A")
        renglones = db.execute(consulta).all()
        if not renglones:
            console.print("[yellow]No hay DgtRutas activas[/yellow]")
            raise Exit(code=0)

    cliente = storage.Client()
    for dgt_ruta, dgt_deposito, autoridad in renglones:
        _obtener_dgt_ruta(db, console, cliente, dgt_ruta, dgt_deposito, autoridad)
