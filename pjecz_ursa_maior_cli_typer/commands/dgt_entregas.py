"""
DGT Entregas commandos
"""

import base64

from google.cloud import storage
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_entregas import DgtEntrega
from pjecz_ursa_maior_cli_typer.models.dgt_entregas_bitacoras import DgtEntregaBitacora
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.models.vsp_digitalizaciones import VspDigitalizacion
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.digitalizaciones import parsear_num_anio_desc
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="DGT Entregas comandos")

DGT_DEPOSITO_PROPOSITO = "ENTREGAS"
DGT_TIPO_CLAVE = "EXP"  # Cuando sea tipo EXPEDIENTE se va a buscar en vsp_digitalizaciones


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
        autoridad = db.execute(select(Autoridad.id).where(Autoridad.clave == autoridad_clave)).first()
        if autoridad is None:
            console.print(f"[red]Autoridad con clave {autoridad_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.where(DgtEntrega.autoridad_id == autoridad.id)
    dgt_ruta_clave = safe_clave(dgt_ruta_clave)
    if dgt_ruta_clave != "":
        dgt_ruta = db.execute(select(DgtRuta.id).where(DgtRuta.clave == dgt_ruta_clave)).first()
        if dgt_ruta is None:
            console.print(f"[red]DGT ruta con clave {dgt_ruta_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.where(DgtEntrega.dgt_ruta_id == dgt_ruta.id)
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
    console.print(f"Depósito: {dgt_deposito.clave.lower()}, Autoridad: {autoridad.clave}, Directorio: {dgt_ruta.directorio}")

    # Inicializar variables
    archivo_urls_en_deposito = set()
    anomalias = creados = modificados = omitidos = eliminados = 0

    # Obtener los blobs para definir el total de blobs para la barra de progreso
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)
    total = sum(1 for _ in blobs)

    # Obtener de nuevo los blobs para iterar sobre ellos, ya que el anterior generador se agotó al contar
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)
    with Progress() as progress:
        task = progress.add_task("Obteniendo entregas...", total=total)

        # Bucle por cada blob en el depósito
        for blob in blobs:
            progress.update(task, advance=1)  # Avanzar la barra de progreso
            if blob.name.endswith("/"):
                continue

            # Saltar si no es el subdirectorio, por ejemplo, entre slt-j2-mer/ y slt-j2-mer-exhorto/
            if not blob.name.startswith(f"{dgt_ruta.directorio}/"):
                continue

            # Obtener información del blob
            archivo_url = f"gs://{dgt_deposito.clave.lower()}/{blob.name}"
            archivo_urls_en_deposito.add(archivo_url)
            archivo_public_url = blob.public_url
            archivo_nombre = blob.name.rsplit("/", maxsplit=1)[-1]
            archivo_md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
            archivo_crc32c = base64.b64decode(blob.crc32c).hex() if blob.crc32c else ""
            archivo_actualizado = blob.updated
            archivo_tamano = blob.size or 0

            # Los nombres de los archivos deben tener número, año y/o descripción
            # Si el número o el año no es válido entrega cero
            # Si no tiene descripción entrega ""
            num, anio, desc = parsear_num_anio_desc(archivo_nombre.split(".")[0])

            # Buscar en dgt_entregas
            dgt_entrega = db.execute(
                select(DgtEntrega)
                .where(DgtEntrega.archivo_url == archivo_url)
            ).scalar_one_or_none()

            # A) No existe, crear un nuevo DgtEntrega
            if dgt_entrega is None:

                # Buscar en vsp_digitalizaciones para saber el UUID
                # Solo se copian los EXHORTOS, por eso solo consultamos ese tipo
                vsp_digitalizacion = None
                if num and anio and dgt_ruta.dgt_tipo.clave == DGT_TIPO_CLAVE:
                    vsp_digitalizacion = db.execute(
                        select(VspDigitalizacion)
                        .where(VspDigitalizacion.autoridad_id == autoridad.id)
                        .where(VspDigitalizacion.expediente_anio == anio)
                        .where(VspDigitalizacion.expediente_num == num)
                        .where(VspDigitalizacion.descripcion == desc)
                    ).scalar_one_or_none()

                # Insertar
                dgt_entrega = DgtEntrega(
                    autoridad_id=autoridad.id,
                    dgt_ruta_id=dgt_ruta.id,
                    archivo_nombre=archivo_nombre,
                    archivo_url=archivo_url,
                    archivo_public_url=archivo_public_url,
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
                    es_anomalo=bool(not num or not anio),
                )
                if vsp_digitalizacion:
                    dgt_entrega.archivo_uuid = vsp_digitalizacion.archivo_uuid
                db.add(dgt_entrega)
                db.flush()

                # Agregar a la bitácora
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

                # Si no es válido el número o el año del expediente, se considera una anomalía
                if not num or not anio:
                    anomalias += 1

                # Continuar
                continue

            # B.1) Ya existe y tiene es_anomalo en None, vamos a actualizarlo a False si sí es válido el número y año
            if dgt_entrega.es_anomalo is None:
                dgt_entrega.es_anomalo = bool(not num or not anio)
                db.add(dgt_entrega)
                if dgt_entrega.es_anomalo:
                    anomalias += 1
                else:
                    modificados += 1
                continue

            # B.2) Ya existe y coincide el md5 y crc32c, omitir
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
            dgt_entrega.ultimo_evento = "MODIFICADO"
            dgt_entrega.ultimo_evento_creado = archivo_actualizado
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
        select(DgtEntrega)
        .where(DgtEntrega.dgt_ruta_id == dgt_ruta.id)
        .where(DgtEntrega.estatus == "A")
    ).scalars()
    for dgt_entrega in dgt_entregas_previas:
        if dgt_entrega.archivo_url in archivo_urls_en_deposito:
            continue
        dgt_entrega.ultimo_evento = "ELIMINADO"
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

    # Mensajes finales
    if anomalias > 0:
        console.print(f"Anomalías: [red]{anomalias}[/red]")
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
        console.print(f"Obteniendo entregas de {dgt_ruta_clave}...")
        consulta = consulta.where(DgtRuta.clave == dgt_ruta_clave).where(DgtRuta.estatus == "A")
        renglones = db.execute(consulta).all()
        if not renglones:
            console.print(f"[red]DgtRuta con clave {dgt_ruta_clave} no encontrada o eliminada[/red]")
            raise Exit(code=1)
    else:
        console.print("Obteniendo entregas de todas las rutas activas...")
        consulta = consulta.where(DgtRuta.estatus == "A")
        renglones = db.execute(consulta).all()
        if not renglones:
            console.print("[yellow]No hay DgtRutas activas[/yellow]")
            raise Exit(code=0)

    cliente = storage.Client()
    for dgt_ruta, dgt_deposito, autoridad in renglones:
        _obtener_dgt_ruta(db, console, cliente, dgt_ruta, dgt_deposito, autoridad)
