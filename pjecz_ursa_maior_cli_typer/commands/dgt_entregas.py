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
from pjecz_ursa_maior_cli_typer.utils.digitalizaciones import parsear_num_anio_desc
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="DGT Entregas comandos")

DGT_DEPOSITO_PROPOSITO = "ENTREGAS"


@app.command()
def consultar(
    autoridad_clave: str = "",
    dgt_ruta_clave: str = "",
    offset: int = 0,
    limit: int = 40,
):
    """Consultar DgtEntrega"""
    console = Console()
    console.print("Consultando DgtEntrega...")
    db = get_database()
    stmt = (
        select(
            DgtEntrega.id,
            Autoridad.clave.label("autoridad_clave"),
            DgtRuta.clave.label("dgt_ruta_clave"),
            DgtEntrega.archivo_nombre,
            DgtEntrega.archivo_tamano,
            DgtEntrega.archivo_actualizado,
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


def _obtener_dgt_ruta(
    db,
    console: Console,
    cliente: storage.Client,
    dgt_ruta: DgtRuta,
    dgt_deposito: DgtDeposito,
    autoridad: Autoridad,
):
    """Rastrear el depósito e insertar o actualizar registros en DgtEntrega de una ruta"""
    console.print(f"Depósito: {dgt_deposito.clave.lower()}, Directorio: {dgt_ruta.directorio}, Autoridad: {autoridad.clave}")

    # Obtener los recursos en el depósito, en el directorio
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)

    # Inicializar variables
    archivo_urls_en_deposito = set()
    creados = modificados = omitidos = eliminados = 0

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

        # Buscar en la base de datos si se tiene ese registro
        consulta = (
            select(DgtEntrega)
            .filter(DgtEntrega.dgt_ruta_id == dgt_ruta.id)
            .filter(DgtEntrega.archivo_url == archivo_url)
        )
        dgt_entrega = db.execute(consulta).scalar_one_or_none()

        # A) No existe una coincidencia, crear un nuevo DgtEntrega
        if dgt_entrega is None:
            num, anio, desc = parsear_num_anio_desc(archivo_nombre.split(".")[0])
            dgt_entrega = DgtEntrega(
                autoridad_id=autoridad.id,
                dgt_ruta_id=dgt_ruta.id,
                archivo_nombre=archivo_nombre,
                archivo_url=archivo_url,
                archivo_md5=archivo_md5,
                archivo_crc32c=archivo_crc32c,
                archivo_actualizado=archivo_actualizado,
                archivo_tamano=archivo_tamano,
                expediente=f"{num}/{anio}" if num and anio else None,
                expediente_anio=anio if anio else None,
                expediente_num=num if num else None,
                descripcion=desc if desc else None,
                ultimo_evento="CREADO",
                ultimo_evento_creado=archivo_actualizado,
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

        # B) Ya existe y coincide el md5 y crc32c, omitir
        if dgt_entrega.archivo_md5 == archivo_md5 and dgt_entrega.archivo_crc32c == archivo_crc32c:
            omitidos += 1
            continue

        # C) Hay diferencias, actualizar y agregar bitácora de MODIFICADO
        archivo_md5_old = dgt_entrega.archivo_md5
        archivo_crc32c_old = dgt_entrega.archivo_crc32c
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

    # D) No están en el depósito, dar de baja y agregar bitácora de ELIMINADO
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

    if creados > 0:
        console.print(f"Creados: [green]{creados}[/green]")
    if modificados > 0:
        console.print(f"Modificados: [yellow]{modificados}[/yellow]")
    if omitidos > 0:
        console.print(f"Omitidos: [gray]{omitidos}[/gray]")
    if eliminados > 0:
        console.print(f"Eliminados: [red]{eliminados}[/red]")


@app.command()
def obtener(dgt_ruta_clave: str = ""):
    """Insertar o actualizar registros en DgtEntrega rastreando el depósito

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
