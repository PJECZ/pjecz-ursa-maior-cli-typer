"""
DGT Entregas commandos
"""

import base64
import logging
import os
from datetime import datetime
from typing import Annotated
from uuid import uuid4

import pytz
from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import storage
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from sqlalchemy import func, select
from typer import Exit, Option, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones import DgtDigitalizacion
from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones_bitacoras import DgtDigitalizacionBitacora
from pjecz_ursa_maior_cli_typer.models.dgt_entregas import DgtEntrega
from pjecz_ursa_maior_cli_typer.models.dgt_entregas_bitacoras import DgtEntregaBitacora
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.models.vsp_digitalizaciones import VspDigitalizacion
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.digitalizaciones import parsear_num_anio_desc
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

COPIAR_PROPOSITO_ORIGEN = "ENTREGAS"  # Los depósitos de DgtEntrega como origen de la copia
COPIAR_PROPOSITO_DESTINO = "DIGITALIZACIONES"  # Los depósitos de DgtDigitalizacion como destino de la copia
DGT_TIPO_CLAVE = "EXP"  # Cuando sea tipo EXPEDIENTE se va a buscar en vsp_digitalizaciones

load_dotenv()  # Cargar variables de entorno desde .env
TZ = pytz.timezone(os.getenv("TZ", "America/Mexico_City"))

app = Typer(help="DGT Entregas comandos")


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
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    stmt = stmt.order_by(DgtEntrega.archivo_actualizado.desc()).offset(offset).limit(limit)
    tabla = Table(title=f"DGT Entregas ({total})")
    #tabla.add_column("ID", header_style="green", no_wrap=True)
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Ruta", header_style="green", no_wrap=True)
    tabla.add_column("Archivo", header_style="green")
    tabla.add_column("Tamaño", header_style="green", justify="right")
    tabla.add_column("Actualizado", header_style="green", no_wrap=True)
    for item in db.execute(stmt):
        tabla.add_row(
            #str(item.id),
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
    bitacora: logging.Logger,
    probar: bool = False,
):
    """Rastrear el depósito e insertar o actualizar registros en DgtEntrega de una ruta"""
    bitacora.info(f"Obteniendo entregas de {dgt_ruta.clave}...")
    console.print(f"Obteniendo entregas de [cyan]{dgt_ruta.clave}[/cyan]...")

    # Inicializar variables
    archivo_urls_en_deposito = set()
    creados = omitidos = 0  # Contadores
    anomalias = []
    eliminados = []
    modificados = []

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
            stmt = select(DgtEntrega).where(DgtEntrega.archivo_url == archivo_url)
            dgt_entrega = db.execute(stmt).scalar_one_or_none()

            # A) No existe, crear un nuevo DgtEntrega
            if dgt_entrega is None:

                # Buscar en vsp_digitalizaciones para saber el UUID
                # Solo se copian los EXHORTOS, por eso solo consultamos ese tipo
                vsp_digitalizacion = None
                if num and anio and dgt_ruta.dgt_tipo.clave == DGT_TIPO_CLAVE:
                    stmt = (
                        select(VspDigitalizacion)
                        .where(VspDigitalizacion.autoridad_id == autoridad.id)
                        .where(VspDigitalizacion.expediente_anio == anio)
                        .where(VspDigitalizacion.expediente_num == num)
                        .where(VspDigitalizacion.descripcion == desc)
                    )
                    vsp_digitalizacion = db.execute(stmt).scalar_one_or_none()

                if probar is False:
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
                    anomalias.append(archivo_url)

                # Continuar
                continue

            # B.1) Ya existe y tiene es_anomalo en None, vamos a actualizarlo a False si sí es válido el número y año
            if dgt_entrega.es_anomalo is None:
                dgt_entrega.es_anomalo = bool(not num or not anio)
                if probar is False:
                    db.add(dgt_entrega)
                    db.flush()
                if dgt_entrega.es_anomalo:
                    anomalias.append(archivo_url)
                else:
                    modificados.append(archivo_url)
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
            if probar is False:
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
            modificados.append(archivo_url)

    # D) No están en el depósito, dar de baja y agregar bitácora de ELIMINADO
    dgt_entregas_previas = db.execute(
        select(DgtEntrega)
        .where(DgtEntrega.dgt_ruta_id == dgt_ruta.id)
        .where(DgtEntrega.estatus == "A")
    ).scalars()
    for dgt_entrega in dgt_entregas_previas:
        if dgt_entrega.archivo_url in archivo_urls_en_deposito:
            continue
        if probar is False:
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
        eliminados.append(archivo_url)

    if probar is False:
        db.commit()

    # Mensajes finales
    prueba = "(PRUEBA) " if probar else ""
    if len(anomalias) > 0:
        for anomalia in anomalias:
            bitacora.warning(f"{prueba}Anomalía: {anomalia}")
            console.print(f"{prueba}Anomalía: [cyan]{anomalia}[/cyan]")
    if len(modificados) > 0:
        for modificado in modificados:
            bitacora.warning(f"{prueba}Modificado: {modificado}")
            console.print(f"{prueba}Modificado: [yellow]{modificado}[/yellow]")
    if len(eliminados) > 0:
        for eliminado in eliminados:
            bitacora.warning(f"{prueba}Eliminado: {eliminado}")
            console.print(f"{prueba}Eliminado: [red]{eliminado}[/red]")
    if creados > 0:
        bitacora.info(f"{prueba}Creados: {creados}")
        console.print(f"{prueba}Creados: [green]{creados}[/green]")
    if omitidos > 0:
        bitacora.info(f"{prueba}Omitidos: {omitidos}")
        console.print(f"{prueba}Omitidos: [gray]{omitidos}[/gray]")


@app.command()
def obtener(
    dgt_ruta_clave: str = "",
    probar: Annotated[bool, Option("--probar", "-p", help="Probar sin guardar en la base de datos")] = False,
):
    """Insertar o actualizar registros en DgtEntrega rastreando el depósito

    Si no se indica la clave de la DgtRuta, se procesan todas las DgtRutas con propósito ENTREGAS y estatus "A".
    """
    ahora = datetime.now(tz=TZ)
    archivo_log = f"logs/dgt-entregas-{ahora.strftime('%Y-%m-%d-%H%M%S')}-obtener.log"
    bitacora = logging.getLogger(__name__)
    bitacora.setLevel(logging.INFO)
    formato = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")
    empunadura = logging.FileHandler(archivo_log)
    empunadura.setFormatter(formato)
    bitacora.addHandler(empunadura)
    console = Console()
    db = get_database()

    stmt = (
        select(DgtRuta, DgtDeposito, Autoridad)
        .join(DgtDeposito)
        .join(Autoridad, Autoridad.clave == DgtRuta.autoridad_clave)
        .where(DgtDeposito.proposito == COPIAR_PROPOSITO_ORIGEN)
    )

    dgt_ruta_clave = safe_clave(dgt_ruta_clave, max_len=64)
    if dgt_ruta_clave != "":
        stmt = stmt.where(DgtRuta.clave == dgt_ruta_clave).where(DgtRuta.estatus == "A")
        renglones = db.execute(stmt).all()
        if not renglones:
            console.print(f"[red]DgtRuta con clave {dgt_ruta_clave} no encontrada o eliminada[/red]")
            raise Exit(code=1)
    else:
        stmt = stmt.where(DgtRuta.estatus == "A")
        renglones = db.execute(stmt).all()
        if not renglones:
            console.print("[yellow]No hay DgtRutas activas[/yellow]")
            raise Exit(code=1)

    cliente = storage.Client()
    for dgt_ruta, dgt_deposito, autoridad in renglones:
        _obtener_dgt_ruta(db, console, cliente, dgt_ruta, dgt_deposito, autoridad, bitacora, probar)


def _buscar_dgt_ruta_destino(db, dgt_ruta_origen: DgtRuta) -> list[DgtRuta]:
    """Buscar las DgtRutas activas de DIGITALIZACIONES con la misma autoridad y tipo que la DgtRuta de origen"""
    return list(
        db.execute(
            select(DgtRuta)
            .join(DgtDeposito)
            .where(DgtDeposito.proposito == COPIAR_PROPOSITO_DESTINO)
            .where(DgtDeposito.estatus == "A")
            .where(DgtRuta.autoridad_clave == dgt_ruta_origen.autoridad_clave)
            .where(DgtRuta.dgt_tipo_id == dgt_ruta_origen.dgt_tipo_id)
            .where(DgtRuta.estatus == "A")
        ).scalars()
    )


def _copiar_dgt_ruta(
    db,
    console: Console,
    cliente: storage.Client,
    dgt_ruta_origen: DgtRuta,
    dgt_ruta_destino: DgtRuta,
    bitacora: logging.Logger,
    probar: bool = False,
):
    """Copiar los archivos de DgtEntrega de una ruta de origen a una ruta de destino e insertar DgtDigitalizacion"""
    deposito_origen = dgt_ruta_origen.dgt_deposito.clave.lower()
    deposito_destino = dgt_ruta_destino.dgt_deposito.clave.lower()
    origen_str = f"{deposito_origen}/{dgt_ruta_origen.directorio}"
    destino_str = f"{deposito_destino}/{dgt_ruta_destino.directorio}"
    bitacora.info(f"Copiando entregas desde {origen_str} hacia digitalizaciones {destino_str}...")
    console.print(f"Copiando entregas desde [cyan]{origen_str}[/cyan] hacia digitalizaciones [cyan]{destino_str}[/cyan]...")

    # Inicializar variables
    copiados = omitidos = no_encontrados = 0  # Contadores

    # Definir los depósitos de Google Cloud Storage
    bucket_origen = cliente.bucket(deposito_origen)
    bucket_destino = cliente.bucket(deposito_destino)

    # Consultar las DgtEntregas, de la ruta de origen, que no sean anómalos, sin importar estatus A o B
    # TODO: Optimizar por ultimo_evento_creado que sea reciente
    stmt = (
        select(
            DgtEntrega.id,
            DgtEntrega.autoridad_id,
            DgtEntrega.archivo_nombre,
            DgtEntrega.archivo_url,
            DgtEntrega.archivo_md5,
            DgtEntrega.archivo_crc32c,
            DgtEntrega.archivo_uuid,
            DgtEntrega.expediente,
            DgtEntrega.expediente_anio,
            DgtEntrega.expediente_num,
            DgtEntrega.descripcion,
            DgtEntrega.ultimo_evento,
            DgtEntrega.estatus,
        )
        .where(DgtEntrega.dgt_ruta_id == dgt_ruta_origen.id)
        .where(DgtEntrega.es_anomalo == False)
        .order_by(DgtEntrega.ultimo_evento_creado)
    )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()

    # Barra de progreso
    with Progress() as progress:
        task = progress.add_task("Copiando entregas a digitalizaciones...", total=total)

        # Bucle por cada DgtEntrega
        for dgt_entrega in db.execute(stmt).all():
            progress.update(task, advance=1)  # Avanzar la barra de progreso

            # Buscar posible DgtDigitalizacion por el UUID de DgtEntrega
            posible_dgt_digitalizacion = None
            if dgt_entrega.archivo_uuid:
                posible_dgt_digitalizacion = db.execute(
                    select(
                        DgtDigitalizacion.id.label("archivo_uuid"),
                        DgtDigitalizacion.archivo_md5,
                        DgtDigitalizacion.archivo_crc32c,
                        DgtDigitalizacion.archivo_url,
                        DgtDigitalizacion.ultimo_evento,
                        DgtDigitalizacion.estatus,
                    )
                    .where(DgtDigitalizacion.id == dgt_entrega.archivo_uuid)
                ).first()

            # ¿Existe su DgtDigitalizacion?...
            archivo_uuid = None
            se_va_a_copiar = False
            ultimo_evento = ""
            if posible_dgt_digitalizacion:
                # Sí existe DgtDigitalizacion
                archivo_uuid = dgt_entrega.archivo_uuid  # Importante conservar el UUID
                # Omitir si está eliminada
                if posible_dgt_digitalizacion.estatus != "A":
                    omitidos += 1
                    continue
                # Comparar elCRC32C y el MD5
                if posible_dgt_digitalizacion.archivo_md5 == dgt_entrega.archivo_md5 and posible_dgt_digitalizacion.archivo_crc32c == dgt_entrega.archivo_crc32c:
                    # Son iguales el CRC32C y el MD5
                    # Si el último evento es igual, se omite
                    if posible_dgt_digitalizacion.ultimo_evento == dgt_entrega.ultimo_evento:
                        omitidos += 1
                        continue
                    # El último evento es diferente
                    # NO se va a copiar
                    se_va_a_copiar = False
                    # Pero SÍ se va a tomar el último evento, posiblemente haya sido ELIMINADO
                    ultimo_evento = posible_dgt_digitalizacion.ultimo_evento
                    bitacora.info(f"Actualizar con {ultimo_evento} para {posible_dgt_digitalizacion.archivo_url}")
                else:
                    # NO coinciden el CRC32C y el MD5, entonces se va a sobreescribir
                    se_va_a_copiar = True
                    ultimo_evento = posible_dgt_digitalizacion.ultimo_evento
                    bitacora.info(f"Sobreescribir con {ultimo_evento} para {posible_dgt_digitalizacion.archivo_url}")
            else:
                # No existe DgtDigitalizacion
                archivo_uuid = uuid4()  # Tal sea nuevo
                # Omitir si está eliminada
                if dgt_entrega.estatus != "A":
                    omitidos += 1
                    continue
                # Si fue es CREADO o MODIFICADO, entonces se va a copiar
                if dgt_entrega.ultimo_evento in ("CREADO", "MODIFICADO"):
                    se_va_a_copiar = True
                    ultimo_evento = "CREADO"
                    bitacora.info(f"Copiar con {ultimo_evento} desde {dgt_entrega.archivo_url}")
                else:
                    # DgtEntrega debe estar ELIMINADO, entonces se omite
                    omitidos += 1
                    continue

            # Definir el nombre del archivo de destino con un UUID, conservando la extensión
            extension = dgt_entrega.archivo_nombre.rsplit(".", maxsplit=1)[-1].lower() if "." in dgt_entrega.archivo_nombre else ""
            archivo_nombre = f"{archivo_uuid}.{extension}" if extension else str(archivo_uuid)
            blob_destino_nombre = f"{dgt_ruta_destino.directorio}/{dgt_entrega.expediente_anio}/{archivo_nombre}"

            # Copiar el archivo
            if probar is False:
                # No se va a copiar, entonces si ya hay DgtDigitalizacion estas columnas no cambian
                if se_va_a_copiar is False and posible_dgt_digitalizacion:
                    archivo_url = posible_dgt_digitalizacion.archivo_url
                    archivo_md5 = posible_dgt_digitalizacion.archivo_md5
                    archivo_crc32c = posible_dgt_digitalizacion.archivo_crc32c
                    archivo_actualizado = posible_dgt_digitalizacion.archivo_actualizado
                    archivo_tamano = posible_dgt_digitalizacion.archivo_tamano

                # Si se va a copiar
                if se_va_a_copiar is True:
                    # Copiar entre depósitos de Google Cloud Storage
                    blob_origen_nombre = dgt_entrega.archivo_url.removeprefix(f"gs://{deposito_origen}/")
                    try:
                        blob = bucket_origen.copy_blob(bucket_origen.blob(blob_origen_nombre), bucket_destino, blob_destino_nombre)
                    except NotFound:
                        no_encontrados += 1
                        continue
                    # Obtener información del archivo copiado
                    archivo_url = f"gs://{deposito_destino}/{blob.name}"
                    archivo_md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
                    archivo_crc32c = base64.b64decode(blob.crc32c).hex() if blob.crc32c else ""
                    archivo_actualizado = blob.updated
                    archivo_tamano = blob.size or 0

                # Si ya tenemos la DgtDigitalizacion
                if posible_dgt_digitalizacion:
                    # Actualizar DgtDigitalizacion
                    stmt = select(DgtDigitalizacion).filter_by(id=posible_dgt_digitalizacion.archivo_uuid)
                    dgt_digitalizacion = db.execute(stmt).scalar_one()
                    dgt_digitalizacion.archivo_md5 = archivo_md5
                    dgt_digitalizacion.archivo_crc32c = archivo_crc32c
                    dgt_digitalizacion.archivo_actualizado = archivo_actualizado
                    dgt_digitalizacion.archivo_tamano = archivo_tamano
                    dgt_digitalizacion.ultimo_evento = ultimo_evento
                    dgt_digitalizacion.ultimo_evento_creado = archivo_actualizado
                    db.add(dgt_digitalizacion)
                    db.flush()
                else:
                    # Insertar DgtDigitalizacion, su ID es el UUID igual que archivo_uuid
                    dgt_digitalizacion = DgtDigitalizacion(
                        id=archivo_uuid,
                        autoridad_id=dgt_entrega.autoridad_id,
                        dgt_ruta_id=dgt_ruta_destino.id,
                        archivo_nombre=archivo_nombre,
                        archivo_url=archivo_url,
                        archivo_public_url=blob.public_url,
                        archivo_md5=archivo_md5,
                        archivo_crc32c=archivo_crc32c,
                        archivo_actualizado=archivo_actualizado,
                        archivo_tamano=archivo_tamano,
                        expediente=dgt_entrega.expediente,
                        expediente_anio=dgt_entrega.expediente_anio,
                        expediente_num=dgt_entrega.expediente_num,
                        descripcion=dgt_entrega.descripcion,
                        ultimo_evento=ultimo_evento,
                        ultimo_evento_creado=archivo_actualizado,
                        es_anomalo=False,
                    )
                    db.add(dgt_digitalizacion)
                    db.flush()

                # Agregar a la bitácora
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
                        evento=ultimo_evento,
                    )
                )

                # Actualizar en DgtEntrega con el UUID para marcar como copiado
                stmt = select(DgtEntrega).filter_by(id=dgt_entrega.id)
                actualizar_dgt_entrega = db.execute(stmt).scalar_one()
                actualizar_dgt_entrega.archivo_uuid = archivo_uuid
                db.add(actualizar_dgt_entrega)
                db.flush()

                # Guardar por cada archivo para que el depósito y la base de datos no se desincronicen
                db.commit()

            # Incrementar el contador de copiados
            copiados += 1

    # Mensajes finales
    prueba = "(PRUEBA) " if probar else ""
    if copiados > 0:
        bitacora.info(f"{prueba}Copiados: {copiados}")
        console.print(f"{prueba}Copiados: [green]{copiados}[/green]")
    if omitidos > 0:
        bitacora.info(f"{prueba}Omitidos: {omitidos}")
        console.print(f"{prueba}Omitidos: [blue]{omitidos}[/blue]")
    if no_encontrados > 0:
        bitacora.info(f"{prueba}No encontrados en el depósito de origen: {no_encontrados}")
        console.print(f"{prueba}No encontrados en el depósito de origen: [red]{no_encontrados}[/red]")


@app.command()
def copiar(
    origen_dgt_ruta_clave: str = "",
    probar: Annotated[bool, Option("--probar", "-p", help="Probar sin guardar en la base de datos")] = False,
):
    """Copiar los archivos de la DgtRuta (origen)

    Del origen su DgtDeposito.proposito debe ser ENTREGAS
    La DgtRuta de destino se determina buscando la de DIGITALIZACIONES con la misma autoridad y tipo que la de origen.
    Del destino su DgtDeposito.proposito debe ser DIGITALIZACIONES
    Si no se indica la clave de la DgtRuta de origen, se procesan todas las DgtRutas con propósito ENTREGAS y estatus "A".
    """
    ahora = datetime.now(tz=TZ)
    archivo_log = f"logs/dgt-entregas-{ahora.strftime('%Y-%m-%d-%H%M%S')}-copiar.log"
    bitacora = logging.getLogger(__name__)
    bitacora.setLevel(logging.INFO)
    formato = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")
    empunadura = logging.FileHandler(archivo_log)
    empunadura.setFormatter(formato)
    bitacora.addHandler(empunadura)
    console = Console()
    db = get_database()

    # Consultar las DgtRutas cuyo propósito sea COPIAR_PROPOSITO_ORIGEN
    stmt = (
        select(DgtRuta)
        .join(DgtDeposito)
        .where(DgtDeposito.proposito == COPIAR_PROPOSITO_ORIGEN)
        .where(DgtRuta.estatus == "A")
    )
    origen_dgt_ruta_clave = safe_clave(origen_dgt_ruta_clave, max_len=64)
    dgt_rutas_origenes = []
    if origen_dgt_ruta_clave != "":
        stmt = stmt.where(DgtRuta.clave == origen_dgt_ruta_clave)
        dgt_ruta_origen = db.scalars(stmt).first()
        if not dgt_ruta_origen:
            console.print(f"[red]DgtRuta de origen {origen_dgt_ruta_clave} no encontrada, eliminada o no es {COPIAR_PROPOSITO_ORIGEN}[/red]")
            raise Exit(code=1)
        dgt_rutas_origenes = [dgt_ruta_origen]
    else:
        stmt = stmt.where(DgtDeposito.estatus == "A")
        dgt_rutas_origenes = db.scalars(stmt).all()
        if not dgt_rutas_origenes:
            console.print(f"[yellow]No hay DgtRutas con {COPIAR_PROPOSITO_ORIGEN} activas[/yellow]")
            raise Exit(code=1)

    # Inicializar cliente de Google Cloud Storage
    cliente = storage.Client()

    # Bucle por cada DgtRuta de origen
    for dgt_ruta_origen in dgt_rutas_origenes:

        # Determinar la DgtRuta de destino, debe existir exactamente una DgtRuta de destino, si no se omite
        candidatos = _buscar_dgt_ruta_destino(db, dgt_ruta_origen)
        if len(candidatos) != 1:
            console.print(
                f"[yellow]Se omite {dgt_ruta_origen.clave} porque NO hay DgtRutas de destino "
                f"con autoridad {dgt_ruta_origen.autoridad_clave} y tipo {dgt_ruta_origen.dgt_tipo.clave}[/yellow]"
            )
            continue

        # Copiar los archivos
        _copiar_dgt_ruta(db, console, cliente, dgt_ruta_origen, candidatos[0], bitacora, probar)
