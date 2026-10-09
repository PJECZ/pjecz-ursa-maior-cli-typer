"""
DGT Digitalizaciones commandos
"""

import base64
import logging
import os
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

import pytz
import requests
from dotenv import load_dotenv
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
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas import DgtPlataforma
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas_autoridades import DgtPlataformaAutoridad
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas_endpoints import DgtPlataformaEndpoint
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas_endpoints_bitacoras import DgtPlataformaEndpointBitacora
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.models.dgt_tipos import DgtTipo
from pjecz_ursa_maior_cli_typer.models.vsp_digitalizaciones import VspDigitalizacion
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.digitalizaciones import es_uuid_valido
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

DGT_DEPOSITO_PROPOSITO = "DIGITALIZACIONES"
DGT_TIPO_CLAVE = "EXP"  # Sólo el tipo EXPEDIENTE se va a buscar en vsp_digitalizaciones o se va a entregar a la DgtPlataforma
TIMEOUT = 30  # Segundos para esperar respuesta de la API

load_dotenv()  # Cargar variables de entorno desde .env
TZ = pytz.timezone(os.getenv("TZ", "America/Mexico_City"))

app = Typer(help="DGT Digitalizaciones comandos")


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
        autoridad = db.execute(select(Autoridad.id).where(Autoridad.clave == autoridad_clave)).first()
        if autoridad is None:
            console.print(f"[red]Autoridad con clave {autoridad_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.where(DgtDigitalizacion.autoridad_id == autoridad.id)
    dgt_ruta_clave = safe_clave(dgt_ruta_clave)
    if dgt_ruta_clave != "":
        dgt_ruta = db.execute(select(DgtRuta.id).where(DgtRuta.clave == dgt_ruta_clave)).first()
        if dgt_ruta is None:
            console.print(f"[red]DGT ruta con clave {dgt_ruta_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.where(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    stmt = stmt.order_by(DgtDigitalizacion.archivo_actualizado.desc()).offset(offset).limit(limit)
    tabla = Table(title=f"DGT Digitalizaciones ({total})")
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
    bitacora: logging.Logger,
    probar: bool = False,
):
    """Rastrear el depósito e insertar o actualizar registros en DgtDigitalizaciones de una ruta"""
    bitacora.info(f"Obtenido digitalizaciones de {dgt_ruta.clave}...")
    console.print(f"Obtenido digitalizaciones de [cyan]{dgt_ruta.clave}[/cyan]...")

    # Inicializar variables
    archivo_urls_en_deposito = set()
    creados = omitidos = 0  # Contadores
    anomalias = []
    eliminados = []
    invalidos = []
    modificados = []
    polizones = []

    # Obtener los blobs para definir el total de blobs para la barra de progreso
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)
    total = sum(1 for _ in blobs)

    # Obtener de nuevo los blobs para iterar sobre ellos, ya que el anterior generador se agotó al contar
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)
    with Progress() as progress:
        task = progress.add_task("Obteniendo archivos del depósito:", total=total)

        # Bucle por cada recurso en el depósito
        for blob in blobs:
            progress.update(task, advance=1)  # Avanzar la barra de progreso
            if blob.name.endswith("/"):
                continue

            # Saltar si no es el subdirectorio, por ejemplo, entre slt-j2-mer/ y slt-j2-mer-exhorto/
            if not blob.name.startswith(f"{dgt_ruta.directorio}/"):
                continue

            # Obtener información del recurso
            archivo_url = f"gs://{dgt_deposito.clave.lower()}/{blob.name}"
            archivo_urls_en_deposito.add(archivo_url)
            archivo_public_url = blob.public_url
            archivo_nombre = blob.name.rsplit("/", maxsplit=1)[-1]
            archivo_md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
            archivo_crc32c = base64.b64decode(blob.crc32c).hex() if blob.crc32c else ""
            archivo_actualizado = blob.updated
            archivo_tamano = blob.size or 0

            # Obtener el UUID a partir del nombre
            archivo_uuid_str = archivo_nombre.rsplit(".", maxsplit=1)[0]
            if es_uuid_valido(archivo_uuid_str) is False:
                # Se encontró un archivo con UUID inválido
                invalidos.append(archivo_url)
                continue
            archivo_uuid = UUID(archivo_uuid_str)

            # Buscar en dgt_digitalizaciones ese UUID
            stmt = select(DgtDigitalizacion).filter_by(id=archivo_uuid)
            dgt_digitalizacion = db.execute(stmt).scalar_one_or_none()

            # A) No existe un registro en dgt_digitalizaciones
            if dgt_digitalizacion is None:
                dgt_entrega = None
                vsp_digitalizacion = None

                # Inicializar variables
                expediente = ""
                expediente_anio = 0
                expediente_num = 0
                descripcion = ""
                ultimo_evento = ""

                # Buscar en dgt_entregas ese UUID
                dgt_entrega = db.execute(
                    select(DgtEntrega)
                    .where(DgtEntrega.archivo_uuid == archivo_uuid)
                ).scalar_one_or_none()

                # Si se encontró en dgt_entregas, tomamos sus datos
                anio_actual = datetime.now(tz=TZ).year
                if dgt_entrega:
                    expediente = dgt_entrega.expediente if dgt_entrega.expediente else None
                    expediente_anio = dgt_entrega.expediente_anio if 1800 <= dgt_entrega.expediente_anio <= anio_actual else None
                    expediente_num = dgt_entrega.expediente_num if dgt_entrega.expediente_num else None
                    descripcion = dgt_entrega.descripcion if dgt_entrega.descripcion else None
                    ultimo_evento = dgt_entrega.ultimo_evento
                else:  # NO se encontró, entonces buscar en vsp_digitalizaciones ese UUID
                    vsp_digitalizacion = db.execute(
                        select(VspDigitalizacion)
                        .where(VspDigitalizacion.archivo_uuid == archivo_uuid)
                    ).scalar_one_or_none()
                    if vsp_digitalizacion:
                        expediente = vsp_digitalizacion.expediente if vsp_digitalizacion.expediente else None
                        expediente_anio = vsp_digitalizacion.expediente_anio if 1800 <= vsp_digitalizacion.expediente_anio <= anio_actual else None
                        expediente_num = vsp_digitalizacion.expediente_num if vsp_digitalizacion.expediente_num else None
                        descripcion = vsp_digitalizacion.descripcion if vsp_digitalizacion.descripcion else None
                        ultimo_evento = "CREADO"
                    else:  # No se encontró en ninguno de los dos, entonces este archivo es un polizón
                        polizones.append(archivo_url)
                        continue

                # Si falta expediante, expediente_anio o expediente_num, entonces es una anomalía
                if not expediente or not expediente_anio or not expediente_num:
                    anomalias.append(archivo_url)
                    continue

                # Si su último evento es ELIMINADO
                if ultimo_evento == "ELIMINADO":
                    eliminados.append(archivo_url)

                # Si su último evento es MODIFICADO
                if ultimo_evento == "MODIFICADO":
                    modificados.append(archivo_url)

                # Si su último evento es CREADO
                if ultimo_evento == "CREADO":
                    creados += 1

                # Insertar dgt_digitalizacion
                if probar is False:
                    nueva_dgt_digitalizacion = DgtDigitalizacion(
                        id=archivo_uuid,
                        autoridad_id = autoridad.id,
                        dgt_ruta_id=dgt_ruta.id,
                        archivo_nombre=archivo_nombre,
                        archivo_url=archivo_url,
                        archivo_public_url=archivo_public_url,
                        archivo_md5=archivo_md5,
                        archivo_crc32c=archivo_crc32c,
                        archivo_actualizado=archivo_actualizado,
                        archivo_tamano=archivo_tamano,
                        expediente=expediente,
                        expediente_anio=expediente_anio,
                        expediente_num=expediente_num,
                        descripcion=descripcion,
                        ultimo_evento=ultimo_evento,
                        ultimo_evento_creado=archivo_actualizado,
                        es_anomalo=False,
                    )
                    db.add(nueva_dgt_digitalizacion)
                    db.flush()
                    db.add(
                        DgtDigitalizacionBitacora(
                            dgt_digitalizacion_id=nueva_dgt_digitalizacion.id,
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

                # Continuar
                continue

            # B.1) Se espera que TODOS tengan año y número de expediente válidos
            # Si es_anomalo es None, entonces actualizar a False
            # Más adelante se programará un proceso para detectar anomalías y actualizar a True
            if dgt_digitalizacion.es_anomalo is None:
                if probar is False:
                    dgt_digitalizacion.es_anomalo = False
                    db.add(dgt_digitalizacion)
                    db.flush()
                continue

            # B.2) Ya existe en dgt_digitalizaciones, si coincide el md5 y crc32c
            if dgt_digitalizacion.archivo_md5 == archivo_md5 and dgt_digitalizacion.archivo_crc32c == archivo_crc32c:
                # TODO: Consultar dgt_entregas para averiguar si fue MODIFICADO o ELIMINADO
                omitidos += 1
                continue

            # C) Hay diferencias en md5 y crc32c, actualizar a MODIFICADO
            archivo_md5_old = dgt_digitalizacion.archivo_md5
            archivo_crc32c_old = dgt_digitalizacion.archivo_crc32c
            if probar is False:
                dgt_digitalizacion.archivo_md5 = archivo_md5
                dgt_digitalizacion.archivo_crc32c = archivo_crc32c
                dgt_digitalizacion.archivo_actualizado = archivo_actualizado
                dgt_digitalizacion.archivo_tamano = archivo_tamano
                dgt_digitalizacion.ultimo_evento = "MODIFICADO"
                dgt_digitalizacion.ultimo_evento_creado = archivo_actualizado
                db.add(dgt_digitalizacion)
                db.flush()
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
            modificados.append(archivo_url)

    # D) No están en el depósito, cambiar estatus a "B" y el evento a ELIMINADO
    stmt = (
        select(DgtDigitalizacion)
        .where(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id)
        .where(DgtDigitalizacion.estatus == "A")
    )
    for dgt_digitalizacion in db.scalars(stmt).all():
        if dgt_digitalizacion.archivo_url in archivo_urls_en_deposito:
            continue
        if probar is False:
            dgt_digitalizacion.ultimo_evento = "ELIMINADO"
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
            db.flush()
        eliminados.append(archivo_url)

    # Guardar cambios en la base de datos
    if probar is False:
        db.commit()

    # Mensajes finales
    prueba = "(PRUEBA) " if probar else ""
    if len(anomalias) > 0:
        for anomalia in anomalias:
            bitacora.info(f"{prueba}Anomalía (fueron omitidos): {anomalia}")
            console.print(f"{prueba}Anomalía (fueron omitidos): [red]{anomalia}[/red]")
    if len(modificados) > 0:
        for modificado in modificados:
            bitacora.info(f"{prueba}Modificado: {modificado}")
            console.print(f"{prueba}Modificado: [yellow]{modificado}[/yellow]")
    if len(eliminados) > 0:
        for eliminado in eliminados:
            bitacora.info(f"{prueba}Eliminado: {eliminado}")
            console.print(f"{prueba}Eliminado: [blue]{eliminado}[/blue]")
    if len(invalidos) > 0:
        for invalido in invalidos:
            bitacora.info(f"{prueba}Cuyo nombre no es un UUID: {invalido}")
            console.print(f"{prueba}Cuyo nombre no es un UUID: [red]{invalido}[/red]")
    if len(polizones) > 0:
        for polizon in polizones:
            bitacora.info(f"{prueba}Están en el depósito pero NO en la BD: {polizon}")
            console.print(f"{prueba}Están en el depósito pero NO en la BD: [red]{polizon}[/red]")
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
    """Insertar o actualizar registros en DgtDigitalizacion rastreando el depósito

    Si no se indica la clave de la DgtRuta, se procesan todas las DgtRutas con propósito ENTREGAS y estatus "A".
    """
    ahora = datetime.now(tz=TZ)
    archivo_log = f"logs/dgt-digitalizaciones-{ahora.strftime('%Y-%m-%d-%H%M%S')}-obtener.log"
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
        .where(DgtDeposito.proposito == DGT_DEPOSITO_PROPOSITO)
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


def _entregar_dgt_ruta(
    db,
    console: Console,
    dgt_ruta: DgtRuta,
    bitacora: logging.Logger,
    probar: bool = False,
):
    """Entregar las DgtDigitalizacion de una DgtRuta a la DgtPlataforma"""
    deposito_origen = dgt_ruta.dgt_deposito.clave.lower()
    bitacora.info(f"Entregando digitalizaciones de {deposito_origen}/{dgt_ruta.directorio}...")
    console.print(f"Entregando digitalizaciones de [cyan]{deposito_origen}/{dgt_ruta.directorio}[/cyan]...")

    # Inicializar variables
    enviados = insertados = omitidos = recibidos = 0  # Contadores

    # Consultar las digitalizaciones en la ruta dada
    digitalizaciones_stmt = (
        select(
            Autoridad.clave.label("autoridad_clave"),
            DgtDigitalizacion.id.label("archivo_uuid"),
            DgtDigitalizacion.expediente,
            DgtDigitalizacion.archivo_public_url.label("url"),
        )
        .join(Autoridad)
        .where(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id)
        .where(DgtDigitalizacion.estatus == "A")
        .where(DgtDigitalizacion.entregado == None)
        .order_by(DgtDigitalizacion.ultimo_evento_creado)
    )

    # Determinar el total para la barra de progreso, salir si no hay digitalizaciones
    digitalizaciones_total = db.execute(select(func.count()).select_from(digitalizaciones_stmt.subquery())).scalar()
    if digitalizaciones_total == 0:
        bitacora.warning(f"No hay digitalizaciones para enviar en {deposito_origen}/{dgt_ruta.directorio}")
        console.print(f"[yellow]No hay digitalizaciones para enviar en {deposito_origen}/{dgt_ruta.directorio}[/yellow]")
        return

    # Consultar la plataforma (API-key y ruta) a partir de autoridad_clave de la ruta
    plataforma_stmt = (
        select(
            DgtPlataforma.api_key,
            DgtPlataforma.descripcion,
            DgtPlataformaEndpoint.id.label("dgt_plataforma_endpoint_id"),
            DgtPlataformaEndpoint.ruta.label("url"),
        )
        .join(DgtPlataformaAutoridad, DgtPlataformaAutoridad.dgt_plataforma_id == DgtPlataforma.id)
        .join(DgtPlataformaEndpoint, DgtPlataformaEndpoint.dgt_plataforma_id == DgtPlataforma.id)
        .join(Autoridad, Autoridad.id == DgtPlataformaAutoridad.autoridad_id)
        .where(Autoridad.clave == dgt_ruta.autoridad_clave)
        .where(DgtPlataformaEndpoint.proposito == "INSERTAR")
        .where(DgtPlataformaEndpoint.metodo == "POST")
    )
    plataforma = db.execute(plataforma_stmt).first()
    if not plataforma:
        bitacora.error(f"No se encontró plataforma para autoridad {dgt_ruta.autoridad_clave}")
        console.print(f"[red]No se encontró plataforma para autoridad {dgt_ruta.autoridad_clave}[/red]")
        return

    # Inicializar el limit y el offset para segmentar los envíos
    limit = 100
    offset = 0

    # Barra de progreso
    with Progress() as progress:
        task = progress.add_task(f"Entregando a {plataforma.descripcion}:", total=digitalizaciones_total)

        # Bucle entre paquetes de envíos
        while offset < digitalizaciones_total:
            dgt_digitalizaciones = db.execute(digitalizaciones_stmt.offset(offset).limit(limit)).all()
            tope = min(offset + limit, digitalizaciones_total)
            bucle_str = f"Desde {offset} hasta {tope} de {digitalizaciones_total}"

            # Armar el payload
            listado = []
            for item in dgt_digitalizaciones:
                listado.append(
                    {
                        "autoridadClave": item.autoridad_clave,
                        "numeroExpediente": item.expediente,
                        "url": item.url,
                    }
                )
            payload = {"digitalizaciones": listado}

            # Enviar el payload a la API de la plataforma
            if probar is False:
                try:
                    respuesta = requests.post(
                        url=plataforma.url,
                        json=payload,
                        headers={"X-Api-Key": plataforma.api_key},
                        timeout=TIMEOUT,
                    )
                    respuesta.raise_for_status()
                except requests.exceptions.ConnectionError:
                    bitacora.error(f"{bucle_str}: No hubo respuesta al tratar de enviar")
                    return
                except requests.exceptions.HTTPError as error:
                    bitacora.error(f"{bucle_str}: Error de estado: {error.response}")
                    return
                except requests.exceptions.RequestException:
                    bitacora.error(f"{bucle_str}: Error desconocido al tratar de enviar")
                    return
                try:
                    datos = respuesta.json()
                except requests.exceptions.JSONDecodeError:
                    bitacora.error(f"{bucle_str}: La respuesta no es JSON")
                    return
                if "success" not in datos:
                    bitacora.error(f"{bucle_str}: La respuesta no tiene success")
                    return

                # Si el success es False, guadar en la bitácora y pasar al siguiente paquete
                # NOTA: Cuando no hay recibidos el success es falso
                if datos["success"] is False:
                    bitacora.warning(f"{bucle_str}: Success es falso: {datos.get('message', 'Sin mensaje')}")
                    db.add(
                        DgtPlataformaEndpointBitacora(
                            dgt_plataforma_endpoint_id=plataforma.dgt_plataforma_endpoint_id,
                            payload=payload,
                            respuesta_codigo=respuesta.status_code,
                            respuesta_exitosa=False,
                            respuesta_mensaje=datos.get("message", "Sin mensaje"),
                            respuesta_datos=datos,
                        )
                    )

                # Procesar la respuesta
                if datos["success"] is True:
                    if datos.get("totalRecibidos"):
                        bitacora.info(f"{bucle_str}: Total recibidos: {datos['totalRecibidos']}")
                        try:
                            recibidos += int(datos["totalRecibidos"])
                        except ValueError:
                            pass
                    if datos.get("totalInsertados"):
                        bitacora.info(f"{bucle_str}: Total insertados: {datos['totalInsertados']}")
                        try:
                            insertados += int(datos["totalInsertados"])
                        except ValueError:
                            pass
                    if datos.get("totalOmitidos"):
                        bitacora.info(f"{bucle_str}: Total omitidos: {datos['totalOmitidos']}")
                        try:
                            omitidos += int(datos["totalOmitidos"])
                        except ValueError:
                            pass

                    # Procesar errores
                    expedientes_omitidos = []
                    if datos.get("errores"):
                        for error in datos["errores"]:
                            # Juntar los expedientes omitidos, ejemplo: "Expediente no encontrado: SLT-J2-MER 456/2024"
                            if error.startswith("Expediente no encontrado:"):
                                # Extraer el 00000/2024 con una expresión regular
                                expediente_omitido = re.search(r"\d+/\d+", error)
                                if expediente_omitido:
                                    expedientes_omitidos.append(expediente_omitido.group())
                            else:
                                bitacora.error(f"{bucle_str}: Error al enviar: {error}")

                    # Guardar en la bitácora los resultados de este paquete
                    db.add(
                        DgtPlataformaEndpointBitacora(
                            dgt_plataforma_endpoint_id=plataforma.dgt_plataforma_endpoint_id,
                            payload=payload,
                            respuesta_codigo=respuesta.status_code,
                            respuesta_exitosa=True,
                            respuesta_mensaje=datos.get("message", "Sin mensaje"),
                            respuesta_datos=datos,
                        )
                    )

                    # Actualizar la columna "entregado" con el tiempo actual
                    if expedientes_omitidos:
                        ahora = datetime.now(tz=TZ)
                        for item in dgt_digitalizaciones:
                            # Los expedientes omitidos no se actualizan, quedarán pendientes para el futuro
                            if item.expediente in expedientes_omitidos:
                                bitacora.warning(f"{bucle_str}: Expediente omitido: {item.expediente}")
                            else:
                                # Actualizar DgtDigitalizacion
                                stmt = select(DgtDigitalizacion).filter_by(id=item.archivo_uuid)
                                dgt_digitalizacion = db.execute(stmt).scalar_one()
                                dgt_digitalizacion.entregado = ahora
                                db.add(dgt_digitalizacion)
                                db.flush()

                    # Aplicar cambios en la base de datos
                    db.commit()

            # Incrementar el offset, el contador de procesados y avanzar la barra de progreso
            offset += limit
            enviados += len(dgt_digitalizaciones)
            progress.update(task, completed=tope)

    # Mensajes finales
    prueba = "(PRUEBA) " if probar else ""
    if enviados > 0:
        bitacora.info(f"{prueba}Enviados: {enviados}")
        console.print(f"{prueba}Enviados: [cyan]{enviados}[/cyan]")
    if insertados > 0:
        bitacora.info(f"{prueba}Insertados: {insertados}")
        console.print(f"{prueba}Insertados: [green]{insertados}[/green]")
    if omitidos > 0:
        bitacora.info(f"{prueba}Omitidos: {omitidos}")
        console.print(f"{prueba}Omitidos: [yellow]{omitidos}[/yellow]")
    if recibidos > 0:
        bitacora.info(f"{prueba}Recibidos: {recibidos}")
        console.print(f"{prueba}Recibidos: [green]{recibidos}[/green]")


@app.command()
def entregar(
    dgt_ruta_clave: str = "",
    probar: Annotated[bool, Option("--probar", "-p", help="Probar sin guardar en la base de datos")] = False,
):
    """Entregar las DgtDigitalizacion a la API de la DgtPlataforma

    Si se especifica la clave de la DgtRuta, se procesará sólo esa ruta.
    - Debe tener propósito DIGITALIZACIONES
    - Debe ser de tipo EXPEDIENTE
    - Debe tener estatus "A"

    Si no se especifica, se procesan todas las DgtRutas con las condiciones anteriores.
    """
    ahora = datetime.now(tz=TZ)
    archivo_log = f"logs/dgt-digitalizaciones-{ahora.strftime('%Y-%m-%d-%H%M%S')}-entregar.log"
    bitacora = logging.getLogger(__name__)
    bitacora.setLevel(logging.INFO)
    formato = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")
    empunadura = logging.FileHandler(archivo_log)
    empunadura.setFormatter(formato)
    bitacora.addHandler(empunadura)
    console = Console()
    db = get_database()

    # Consultar las DgtRutas con propósito DGT_DEPOSITO_PROPOSITO y DGT_TIPO_CLAVE
    stmt = (
        select(DgtRuta)
        .join(DgtDeposito)
        .join(DgtTipo)
        .where(DgtDeposito.proposito == DGT_DEPOSITO_PROPOSITO)
        .where(DgtTipo.clave == DGT_TIPO_CLAVE)
        .where(DgtRuta.estatus == "A")
    )

    # Si viene dgt_ruta_clave
    dgt_ruta_clave = safe_clave(dgt_ruta_clave, max_len=64)
    if dgt_ruta_clave != "":
        stmt = stmt.where(DgtRuta.clave == dgt_ruta_clave)
        dgt_rutas = db.scalars(stmt).all()
        if not dgt_rutas:
            console.print(f"[red]DgtRuta con clave {dgt_ruta_clave} no encontrada, eliminada o no es {DGT_DEPOSITO_PROPOSITO}[/red]")
            raise Exit(code=1)
    else:
        dgt_rutas = db.scalars(stmt).all()
        if not dgt_rutas:
            console.print(f"[yellow]No hay DgtRutas con {DGT_DEPOSITO_PROPOSITO} y tipo {DGT_TIPO_CLAVE} activas[/yellow]")
            raise Exit(code=1)

    # Bucle por cada DgtRuta
    for dgt_ruta in dgt_rutas:
        _entregar_dgt_ruta(db, console, dgt_ruta, bitacora, probar)
