"""
DGT Entregas commandos
"""

import base64

from google.cloud import storage
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_entregas import DgtEntrega
from pjecz_ursa_maior_cli_typer.models.dgt_entregas_bitacoras import DgtEntregaBitacora
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


@app.command()
def obtener(dgt_ruta_clave: str):
    """Rastrear el depósito en Google Cloud Storage e insertar o actualizar registros en DgtEntrega"""
    console = Console()
    console.print("Obteniendo DGT entregas...")
    db = get_database()

    dgt_ruta_clave = safe_clave(dgt_ruta_clave)
    if dgt_ruta_clave == "":
        console.print("[red]Debe indicar la clave de la DGT ruta[/red]")
        raise Exit(code=1)
    renglon = db.execute(
        select(DgtRuta, DgtDeposito, Autoridad)
        .join(DgtDeposito)
        .join(Autoridad, Autoridad.clave == DgtRuta.autoridad_clave)
        .filter(DgtRuta.clave == dgt_ruta_clave)
    ).first()
    if renglon is None:
        console.print(f"[red]DGT ruta con clave {dgt_ruta_clave} no encontrada[/red]")
        raise Exit(code=1)
    dgt_ruta, dgt_deposito, autoridad = renglon

    console.print(f"Depósito: {dgt_deposito.clave}, Directorio: {dgt_ruta.directorio}, Autoridad: {autoridad.clave}")

    cliente = storage.Client()
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)

    archivo_urls_en_deposito = set()
    creados = modificados = omitidos = 0

    for blob in blobs:
        if blob.name.endswith("/"):
            continue
        archivo_url = f"gs://{dgt_deposito.clave.lower()}/{blob.name}"
        archivo_urls_en_deposito.add(archivo_url)
        archivo_nombre = blob.name.rsplit("/", maxsplit=1)[-1]
        archivo_md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
        archivo_crc32c = base64.b64decode(blob.crc32c).hex() if blob.crc32c else ""
        archivo_actualizado = blob.updated
        archivo_tamano = blob.size or 0

        dgt_entrega = db.execute(
            select(DgtEntrega)
            .filter(DgtEntrega.dgt_ruta_id == dgt_ruta.id)
            .filter(DgtEntrega.archivo_url == archivo_url)
        ).scalar_one_or_none()

        # A) No existe una coincidencia, crear un nuevo DgtEntrega
        if dgt_entrega is None:
            dgt_entrega = DgtEntrega(
                autoridad_id=autoridad.id,
                dgt_ruta_id=dgt_ruta.id,
                archivo_nombre=archivo_nombre,
                archivo_url=archivo_url,
                archivo_md5=archivo_md5,
                archivo_crc32c=archivo_crc32c,
                archivo_actualizado=archivo_actualizado,
                archivo_tamano=archivo_tamano,
            )
            db.add(dgt_entrega)
            db.flush()
            db.add(
                DgtEntregaBitacora(
                    dgt_entrega_id=dgt_entrega.id,
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

        # B) Ya existe y coincide el md5, crc32c, actualizado y tamaño, omitir
        if (
            dgt_entrega.archivo_md5 == archivo_md5
            and dgt_entrega.archivo_crc32c == archivo_crc32c
            and dgt_entrega.archivo_actualizado == archivo_actualizado
            and dgt_entrega.archivo_tamano == archivo_tamano
        ):
            omitidos += 1
            continue

        # C) Hay diferencias, actualizar y agregar bitácora de MODIFICADO
        archivo_md5_old = dgt_entrega.archivo_md5
        archivo_crc32c_old = dgt_entrega.archivo_crc32c
        dgt_entrega.archivo_nombre = archivo_nombre
        dgt_entrega.archivo_md5 = archivo_md5
        dgt_entrega.archivo_crc32c = archivo_crc32c
        dgt_entrega.archivo_actualizado = archivo_actualizado
        dgt_entrega.archivo_tamano = archivo_tamano
        db.add(dgt_entrega)
        db.add(
            DgtEntregaBitacora(
                dgt_entrega_id=dgt_entrega.id,
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

    # D) DgtEntrega que ya no están en el depósito, dar de baja y agregar bitácora de ELIMINADO
    eliminados = 0
    dgt_entregas_previas = db.execute(
        select(DgtEntrega).filter(DgtEntrega.dgt_ruta_id == dgt_ruta.id).filter(DgtEntrega.estatus == "A")
    ).scalars()
    for dgt_entrega in dgt_entregas_previas:
        if dgt_entrega.archivo_url in archivo_urls_en_deposito:
            continue
        dgt_entrega.estatus = "B"
        db.add(dgt_entrega)
        db.add(
            DgtEntregaBitacora(
                dgt_entrega_id=dgt_entrega.id,
                archivo_url=dgt_entrega.archivo_url,
                archivo_md5_old=dgt_entrega.archivo_md5,
                archivo_md5_new="",
                archivo_crc32c_old=dgt_entrega.archivo_crc32c,
                archivo_crc32c_new="",
                archivo_actualizado=dgt_entrega.archivo_actualizado,
                archivo_tamano=dgt_entrega.archivo_tamano,
                evento="ELIMINADO",
            )
        )
        eliminados += 1

    db.commit()

    console.print(f"[green]Creados: {creados}[/green]")
    console.print(f"[yellow]Modificados: {modificados}[/yellow]")
    console.print(f"Omitidos: {omitidos}")
    console.print(f"[red]Eliminados: {eliminados}[/red]")
