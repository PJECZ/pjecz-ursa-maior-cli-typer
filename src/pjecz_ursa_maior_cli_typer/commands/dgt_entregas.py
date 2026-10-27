"""
DGT Entregas commandos
"""

import base64
import logging
from datetime import datetime
from typing import Annotated

import pytz
from google.cloud import storage
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer import Option, Typer

from pjecz_ursa_maior_cli_typer.config.settings import get_settings
from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.digitalizaciones import parsear_num_anio_desc
from pjecz_ursa_maior_cli_typer.core.exceptions import MyNotValidParamError
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave
from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_entregas import DgtEntrega
from pjecz_ursa_maior_cli_typer.models.dgt_entregas_bitacoras import DgtEntregaBitacora
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta

PROPOSITO = "ENTREGAS"  # Sólo se procesan los depósitos con este propósito

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
    tabla.add_column("Actualizado", header_style="green", no_wrap=True)
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Ruta", header_style="green", no_wrap=True)
    tabla.add_column("Archivo", header_style="green")
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


def _agregar_bitacora(session: Session, dgt_entrega: DgtEntrega, evento: str, md5_old: str = "", crc32c_old: str = ""):
    """Agregar un registro a la bitácora con los datos actuales del DgtEntrega"""
    eliminado = evento == "ELIMINADO"
    session.add(
        DgtEntregaBitacora(
            dgt_entrega_id=dgt_entrega.id,
            archivo_url=dgt_entrega.archivo_url,
            archivo_md5_old=md5_old,
            archivo_md5_new="" if eliminado else dgt_entrega.archivo_md5,
            archivo_crc32c_old=crc32c_old,
            archivo_crc32c_new="" if eliminado else dgt_entrega.archivo_crc32c,
            archivo_actualizado=dgt_entrega.archivo_actualizado,
            archivo_tamano=dgt_entrega.archivo_tamano,
            evento=evento,
        )
    )


def _obtener_dgt_ruta(
    console: Console,
    bitacora: logging.Logger,
    cliente: storage.Client,
    dgt_ruta_id,
    probar: bool,
):
    """Empatar los registros de DgtEntrega de una ruta con los archivos en el depósito"""
    with session_scope() as session:
        dgt_ruta = session.get(DgtRuta, dgt_ruta_id)
        deposito = dgt_ruta.dgt_deposito.clave.lower()
        directorio = dgt_ruta.directorio.strip("/")
        autoridad_id = session.execute(select(Autoridad.id).where(Autoridad.clave == dgt_ruta.autoridad_clave)).scalar_one()
        bitacora.info(f"Obteniendo entregas de {dgt_ruta.clave}...")
        console.print(f"Obteniendo entregas de [cyan]{dgt_ruta.clave}[/cyan]...")

        # Inicializar contadores y listados
        omitidos = 0
        creados = []
        anomalias = []
        eliminados = []
        modificados = []

        # Consultar los DgtEntrega de la ruta, indexados por su URL
        dgt_entregas = {
            dgt_entrega.archivo_url: dgt_entrega
            for dgt_entrega in session.execute(
                select(DgtEntrega).where(DgtEntrega.dgt_ruta_id == dgt_ruta.id).where(DgtEntrega.estatus == "A")
            ).scalars()
        }

        # Obtener los blobs, la diagonal al final evita mezclar slt-j2-mer/ con slt-j2-mer-exhorto/
        blobs = [blob for blob in cliente.list_blobs(deposito, prefix=f"{directorio}/") if not blob.name.endswith("/")]
        archivo_urls_en_deposito = set()

        with Progress() as progress:
            task = progress.add_task("Obteniendo entregas:", total=len(blobs))

            for blob in blobs:
                progress.update(task, advance=1)

                # Obtener información del blob
                archivo_url = f"gs://{deposito}/{blob.name}"
                archivo_urls_en_deposito.add(archivo_url)
                archivo_nombre = blob.name.rsplit("/", maxsplit=1)[-1]
                archivo_md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
                archivo_crc32c = base64.b64decode(blob.crc32c).hex() if blob.crc32c else ""
                archivo_actualizado = blob.updated
                archivo_tamano = blob.size or 0

                # Separar el número, el año y la descripción, si el número o el año no son válidos entrega cero
                num, anio, desc = parsear_num_anio_desc(archivo_nombre.rsplit(".", maxsplit=1)[0])
                es_anomalo = not num or not anio

                dgt_entrega = dgt_entregas.get(archivo_url)

                # A) No existe, crear un nuevo DgtEntrega con el evento CREADO
                if dgt_entrega is None:
                    creados.append(archivo_url)
                    if es_anomalo:
                        anomalias.append(archivo_url)
                    if probar:
                        continue
                    dgt_entrega = DgtEntrega(
                        autoridad_id=autoridad_id,
                        dgt_ruta_id=dgt_ruta.id,
                        archivo_nombre=archivo_nombre,
                        archivo_url=archivo_url,
                        archivo_public_url=blob.public_url,
                        archivo_md5=archivo_md5,
                        archivo_crc32c=archivo_crc32c,
                        archivo_actualizado=archivo_actualizado,
                        archivo_tamano=archivo_tamano,
                        expediente=f"{num}/{anio}" if not es_anomalo else None,
                        expediente_anio=anio or None,
                        expediente_num=num or None,
                        descripcion=desc or None,
                        es_anomalo=es_anomalo,
                        ultimo_evento="CREADO",
                        ultimo_evento_creado=archivo_actualizado,
                    )
                    session.add(dgt_entrega)
                    session.flush()
                    _agregar_bitacora(session, dgt_entrega, "CREADO")
                    continue

                # B) Ya existe, coinciden el md5 y el crc32c y no fue eliminado, omitir
                if (
                    dgt_entrega.archivo_md5 == archivo_md5
                    and dgt_entrega.archivo_crc32c == archivo_crc32c
                    and dgt_entrega.ultimo_evento != "ELIMINADO"
                ):
                    omitidos += 1
                    continue

                # C) Ya existe pero cambió (o reapareció tras ser eliminado), actualizar con el evento MODIFICADO
                modificados.append(archivo_url)
                if probar:
                    continue
                md5_old = dgt_entrega.archivo_md5
                crc32c_old = dgt_entrega.archivo_crc32c
                dgt_entrega.archivo_public_url = blob.public_url
                dgt_entrega.archivo_md5 = archivo_md5
                dgt_entrega.archivo_crc32c = archivo_crc32c
                dgt_entrega.archivo_actualizado = archivo_actualizado
                dgt_entrega.archivo_tamano = archivo_tamano
                dgt_entrega.ultimo_evento = "MODIFICADO"
                dgt_entrega.ultimo_evento_creado = archivo_actualizado
                _agregar_bitacora(session, dgt_entrega, "MODIFICADO", md5_old, crc32c_old)

        # D) Están en la base de datos como CREADO o MODIFICADO pero ya no en el depósito, actualizar con el evento ELIMINADO
        for archivo_url, dgt_entrega in dgt_entregas.items():
            if archivo_url in archivo_urls_en_deposito or dgt_entrega.ultimo_evento not in ("CREADO", "MODIFICADO"):
                continue
            eliminados.append(archivo_url)
            if probar:
                continue
            dgt_entrega.ultimo_evento = "ELIMINADO"
            dgt_entrega.ultimo_evento_creado = datetime.now(tz=pytz.UTC)
            _agregar_bitacora(session, dgt_entrega, "ELIMINADO", dgt_entrega.archivo_md5, dgt_entrega.archivo_crc32c)

    # Mostrar los listados y los contadores
    prueba = "[yellow](PRUEBA)[/yellow] " if probar else ""
    prueba_log = "(PRUEBA) " if probar else ""
    for anomalia in anomalias:
        bitacora.warning(f"{prueba_log}Anomalía: {anomalia}")
        console.print(f"{prueba}Anomalía: [cyan]{anomalia}[/cyan]")
    for modificado in modificados:
        bitacora.warning(f"{prueba_log}Modificado: {modificado}")
        console.print(f"{prueba}Modificado: [yellow]{modificado}[/yellow]")
    for eliminado in eliminados:
        bitacora.warning(f"{prueba_log}Eliminado: {eliminado}")
        console.print(f"{prueba}Eliminado: [red]{eliminado}[/red]")
    for creado in creados:
        bitacora.info(f"{prueba_log}Creado: {creado}")
    resumen = (
        f"Creados: {len(creados)}, Modificados: {len(modificados)}, Eliminados: {len(eliminados)}, "
        f"Anomalías: {len(anomalias)}, Omitidos: {omitidos}"
    )
    bitacora.info(f"{prueba_log}{resumen}")
    console.print(
        f"{prueba}Creados: [green]{len(creados)}[/green], Modificados: [yellow]{len(modificados)}[/yellow], "
        f"Eliminados: [red]{len(eliminados)}[/red], Anomalías: [cyan]{len(anomalias)}[/cyan], Omitidos: {omitidos}"
    )


@app.command()
def obtener(
    dgt_deposito_clave: str | None = None,
    dgt_ruta_clave: str | None = None,
    probar: Annotated[bool, Option("--probar", "-p", help="Probar sin guardar en la base de datos")] = False,
):
    """Insertar o actualizar entregas a partir de los archivos en los depósitos

    Si proporciona la clave del depósito, se procesan todas las rutas (no eliminadas) del mismo.
    Si proporciona la clave de la ruta, se procesa sólo esa ruta.
    Si ninguna de las anteriores se da, se procesan todas las rutas (no eliminadas) de los depósitos.
    Siempre procesa depósitos con propósito ENTREGAS.
    """
    console = Console()

    # Bitácora en un archivo log
    settings = get_settings()
    tz = pytz.timezone(settings.TZ)
    ahora = datetime.now(tz=tz)
    archivo_log = f"logs/dgt-entregas-{ahora.strftime('%Y-%m-%d-%H%M%S')}-obtener.log"
    bitacora = logging.getLogger(__name__)
    bitacora.setLevel(logging.INFO)
    formato = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")
    empunadura = logging.FileHandler(archivo_log)
    empunadura.setFormatter(formato)
    bitacora.addHandler(empunadura)

    # Cláusulas where
    where_clauses = [DgtRuta.estatus == "A", DgtDeposito.estatus == "A", DgtDeposito.proposito == PROPOSITO]
    if dgt_ruta_clave and (dgt_ruta_clave := safe_clave(dgt_ruta_clave, max_len=64)):
        where_clauses.append(DgtRuta.clave == dgt_ruta_clave)
    elif dgt_deposito_clave and (dgt_deposito_clave := safe_clave(dgt_deposito_clave, max_len=64)):
        where_clauses.append(DgtDeposito.clave == dgt_deposito_clave)

    # Consultar las rutas
    stmt = (
        select(DgtRuta.id)
        .select_from(DgtRuta)
        .join(DgtDeposito, DgtRuta.dgt_deposito_id == DgtDeposito.id)
        .where(*where_clauses)
        .order_by(DgtRuta.clave)
    )
    with session_scope() as session:
        dgt_rutas_ids = session.execute(stmt).scalars().all()
    if not dgt_rutas_ids:
        raise MyNotValidParamError(f"No hay rutas activas en depósitos con propósito {PROPOSITO} con esos parámetros")

    # Procesar cada ruta, cada una se guarda en su propia transacción
    cliente = storage.Client()
    for dgt_ruta_id in dgt_rutas_ids:
        _obtener_dgt_ruta(console, bitacora, cliente, dgt_ruta_id, probar)
