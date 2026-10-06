"""
DGT Entregas commandos
"""

import base64
from typing import Annotated
from uuid import uuid4

from google.api_core.exceptions import NotFound
from google.cloud import storage
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from sqlalchemy import select
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

app = Typer(help="DGT Entregas comandos")

COPIAR_PROPOSITO_ORIGEN = "ENTREGAS"  # Los depósitos de DgtEntrega
COPIAR_PROPOSITO_DESTINO = "DIGITALIZACIONES"  # Los depósitos de DgtDigitalizacion
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
        .where(DgtDeposito.proposito == COPIAR_PROPOSITO_ORIGEN)
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
    probar: bool = False,
):
    """Copiar los archivos de DgtEntrega de una ruta de origen a una ruta de destino e insertar DgtDigitalizacion"""
    deposito_origen = dgt_ruta_origen.dgt_deposito.clave.lower()
    deposito_destino = dgt_ruta_destino.dgt_deposito.clave.lower()
    console.print(f"Origen: [gray]{deposito_origen}/{dgt_ruta_origen.directorio}[/gray]")
    console.print(f"Destino: [green]{deposito_destino}/{dgt_ruta_destino.directorio}[/green]")

    # Inicializar variables
    copiados = omitidos = no_encontrados = 0
    bucket_origen = cliente.bucket(deposito_origen)
    bucket_destino = cliente.bucket(deposito_destino)

    # Consultar las DgtEntregas activas de la ruta de origen
    # TODO: Para optimizar podríamos filtrar...
    # - Aquellos cuyo ultimo_evento_creado sea reciente
    # - Aquellos cuyo archivo_uuid sea None
    # - Descartar aquellos con es_anomalo sea True o None
    dgt_entregas = db.execute(
        select(DgtEntrega)
        .where(DgtEntrega.dgt_ruta_id == dgt_ruta_origen.id)
        .where(DgtEntrega.estatus == "A")
        .order_by(DgtEntrega.ultimo_evento_creado)
    ).scalars().all()

    with Progress() as progress:
        task = progress.add_task("Copiando archivos...", total=len(dgt_entregas))

        # Bucle por cada DgtEntrega
        for dgt_entrega in dgt_entregas:
            progress.update(task, advance=1)  # Avanzar la barra de progreso

            # Omitir si es anómalo o si no se sabe si lo es
            if dgt_entrega.es_anomalo is not False:
                omitidos += 1
                continue

            # Omitir si ya fue copiado
            if dgt_entrega.archivo_uuid is not None:
                omitidos += 1
                continue

            # Definir el nombre del archivo de destino con un UUID, conservando la extensión
            archivo_uuid = uuid4()
            extension = dgt_entrega.archivo_nombre.rsplit(".", maxsplit=1)[-1].lower() if "." in dgt_entrega.archivo_nombre else ""
            archivo_nombre = f"{archivo_uuid}.{extension}" if extension else str(archivo_uuid)
            blob_destino_nombre = f"{dgt_ruta_destino.directorio}/{archivo_nombre}"

            # Copiar el archivo en el depósito
            if probar is False:
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

                # Insertar DgtDigitalizacion, su ID es el mismo UUID del nombre del archivo
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
                    ultimo_evento="CREADO",
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
                        evento="CREADO",
                    )
                )

                # Recordar en DgtEntrega que ya fue copiado
                dgt_entrega.archivo_uuid = archivo_uuid
                db.add(dgt_entrega)

                # Guardar por cada archivo para que el depósito y la base de datos no se desincronicen
                db.commit()

            # Incrementar el contador de copiados
            copiados += 1

    # Mensajes finales
    if copiados > 0:
        if probar:
            console.print(f"Se pueden copiar (prueba): [green]{copiados}[/green]")
        else:
            console.print(f"Copiados: [green]{copiados}[/green]")
    if omitidos > 0:
        console.print(f"Omitidos: [gray]{omitidos}[/gray]")
    if no_encontrados > 0:
        console.print(f"No encontrados en el depósito de origen: [red]{no_encontrados}[/red]")


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
    console = Console()
    db = get_database()

    # Consultar las DgtRutas de origen
    consulta = (
        select(DgtRuta)
        .join(DgtDeposito)
        .where(DgtDeposito.proposito == COPIAR_PROPOSITO_ORIGEN)
        .where(DgtRuta.estatus == "A")
    )
    origen_dgt_ruta_clave = safe_clave(origen_dgt_ruta_clave, max_len=64)
    if origen_dgt_ruta_clave != "":
        console.print(f"Copiando entregas de {origen_dgt_ruta_clave}...")
        dgt_rutas_origen = db.execute(consulta.where(DgtRuta.clave == origen_dgt_ruta_clave)).scalars().all()
        if not dgt_rutas_origen:
            console.print(f"[red]DgtRuta de origen {origen_dgt_ruta_clave} no encontrada, eliminada o no es {COPIAR_PROPOSITO_ORIGEN}[/red]")
            raise Exit(code=1)
    else:
        console.print(f"Copiando todas las rutas activas con {COPIAR_PROPOSITO_ORIGEN}...")
        consulta = consulta.where(DgtDeposito.estatus == "A")
        dgt_rutas_origen = db.execute(consulta).scalars().all()
        if not dgt_rutas_origen:
            console.print(f"[yellow]No hay DgtRutas con {COPIAR_PROPOSITO_ORIGEN} activas[/yellow]")
            raise Exit(code=0)

    # Inicializar cliente de Google Cloud Storage
    cliente = storage.Client()

    # Bucle por cada DgtRuta de origen
    for dgt_ruta_origen in dgt_rutas_origen:

        # Determinar la DgtRuta de destino, debe existir exactamente una DgtRuta de destino, si no se omite
        candidatos = _buscar_dgt_ruta_destino(db, dgt_ruta_origen)
        if len(candidatos) != 1:
            console.print(
                f"[yellow]Se omite {dgt_ruta_origen.clave}: se encontraron {len(candidatos)} DgtRutas de destino "
                f"con autoridad {dgt_ruta_origen.autoridad_clave} y tipo {dgt_ruta_origen.dgt_tipo.clave}[/yellow]"
            )
            continue

        # Copiar los archivos
        _copiar_dgt_ruta(db, console, cliente, dgt_ruta_origen, candidatos[0], probar)
