"""
DGT Digitalizaciones commandos
"""

import base64
import logging
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

import pytz
import requests
from google.cloud import storage
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer import Option, Typer

from pjecz_ursa_maior_cli_typer.config.settings import get_settings
from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.digitalizaciones import es_uuid_valido
from pjecz_ursa_maior_cli_typer.core.exceptions import MyNotValidParamError
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave
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

PROPOSITO = "DIGITALIZACIONES"  # Sólo se procesan los depósitos con este propósito

app = Typer(help="DGT Digitalizaciones comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    autoridad_clave: str | None = None,
    dgt_ruta_clave: str | None = None,
    es_anomalo: bool | None = None,
):
    """Consultar digitalizaciones"""
    console = Console()
    console.print("Consultando digitalizaciones...")

    # Preparar tabla
    tabla = Table(title="DGT Digitalizaciones")
    tabla.add_column("Autoridad", header_style="green", no_wrap=True)
    tabla.add_column("Ruta", header_style="green", no_wrap=True)
    tabla.add_column("Archivo", header_style="green")
    tabla.add_column("Actualizado", header_style="green", no_wrap=True)
    tabla.add_column("Tamaño", header_style="green", no_wrap=True, justify="right")
    tabla.add_column("Último evento", header_style="green", no_wrap=True)
    tabla.add_column("Es anómalo", header_style="green", no_wrap=True)

    # Cláusulas where
    where_clauses = [DgtDigitalizacion.estatus == "A"]
    if autoridad_clave and (autoridad_clave := safe_clave(autoridad_clave, max_len=64)):
        where_clauses.append(Autoridad.clave == autoridad_clave)
    if dgt_ruta_clave and (dgt_ruta_clave := safe_clave(dgt_ruta_clave, max_len=64)):
        where_clauses.append(DgtRuta.clave == dgt_ruta_clave)
    if es_anomalo is not None:
        where_clauses.append(DgtDigitalizacion.es_anomalo == es_anomalo)

    # Sentencia
    stmt = (
        select(
            Autoridad.clave.label("autoridad_clave"),
            DgtRuta.clave.label("dgt_ruta_clave"),
            DgtDigitalizacion.archivo_nombre,
            DgtDigitalizacion.archivo_actualizado,
            DgtDigitalizacion.archivo_tamano,
            DgtDigitalizacion.ultimo_evento,
            DgtDigitalizacion.es_anomalo,
        )
        .select_from(DgtDigitalizacion)
        .join(Autoridad, DgtDigitalizacion.autoridad_id == Autoridad.id)
        .join(DgtRuta, DgtDigitalizacion.dgt_ruta_id == DgtRuta.id)
        .where(*where_clauses)
        .order_by(DgtDigitalizacion.archivo_actualizado.desc())
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


def _agregar_bitacora_al_obtener(
    session: Session,
    dgt_digitalizacion: DgtDigitalizacion,
    evento: str,
    md5_old: str = "",
    crc32c_old: str = "",
):
    """Agregar un registro a la bitácora con los datos actuales del DgtDigitalizacion"""
    eliminado = evento == "ELIMINADO"
    session.add(
        DgtDigitalizacionBitacora(
            dgt_digitalizacion_id=dgt_digitalizacion.id,
            archivo_url=dgt_digitalizacion.archivo_url,
            archivo_md5_old=md5_old,
            archivo_md5_new="" if eliminado else dgt_digitalizacion.archivo_md5,
            archivo_crc32c_old=crc32c_old,
            archivo_crc32c_new="" if eliminado else dgt_digitalizacion.archivo_crc32c,
            archivo_actualizado=dgt_digitalizacion.archivo_actualizado,
            archivo_tamano=dgt_digitalizacion.archivo_tamano,
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
    """Empatar los registros de DgtDigitalizacion de una ruta con los archivos en el depósito"""
    with session_scope() as session:
        dgt_ruta = session.get(DgtRuta, dgt_ruta_id)
        deposito = dgt_ruta.dgt_deposito.clave.lower()
        directorio = dgt_ruta.directorio.strip("/")
        autoridad_id = session.execute(select(Autoridad.id).where(Autoridad.clave == dgt_ruta.autoridad_clave)).scalar_one()
        bitacora.info(f"Obteniendo digitalizaciones de {dgt_ruta.clave}...")
        console.print(f"Obteniendo digitalizaciones de [cyan]{dgt_ruta.clave}[/cyan]...")

        # Inicializar contadores y listados
        omitidos = 0
        creados = []
        anomalias = []
        eliminados = []
        modificados = []
        invalidos = []  # No tienen UUID válido

        # Consultar los DgtDigitalizacion de la ruta, indexados por su UUID
        dgt_digitalizaciones = {
            dgt_digitalizacion.id: dgt_digitalizacion
            for dgt_digitalizacion in session.execute(
                select(DgtDigitalizacion)
                .where(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id)
                .where(DgtDigitalizacion.estatus == "A")
            ).scalars()
        }

        # Obtener los blobs, la diagonal al final evita mezclar slt-j2-mer/ con slt-j2-mer-exhorto/
        blobs = [blob for blob in cliente.list_blobs(deposito, prefix=f"{directorio}/") if not blob.name.endswith("/")]
        archivo_uuids_en_deposito = set()

        # Barra de progreso
        with Progress() as progress:
            task = progress.add_task("Obteniendo digitalizaciones:", total=len(blobs))

            # Bucle por cada archivo en el depósito en la ruta dada
            for blob in blobs:
                progress.update(task, advance=1)

                # Obtener información del blob
                archivo_url = f"gs://{deposito}/{blob.name}"
                archivo_nombre = blob.name.rsplit("/", maxsplit=1)[-1]
                archivo_md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else ""
                archivo_crc32c = base64.b64decode(blob.crc32c).hex() if blob.crc32c else ""
                archivo_actualizado = blob.updated
                archivo_tamano = blob.size or 0

                # Obtener el UUID a partir del nombre, sin la extensión
                archivo_uuid_str = archivo_nombre.rsplit(".", maxsplit=1)[0]
                if not es_uuid_valido(archivo_uuid_str):
                    invalidos.append(archivo_url)
                    continue
                archivo_uuid = UUID(archivo_uuid_str)
                archivo_uuids_en_deposito.add(archivo_uuid)

                # Obtener el registro de la digitalización
                dgt_digitalizacion = dgt_digitalizaciones.get(archivo_uuid)

                # A) No existe, crear un nuevo DgtDigitalizacion con el evento CREADO
                if dgt_digitalizacion is None:
                    # Si el UUID ya está en otra ruta no se puede insertar, es una anomalía
                    if session.get(DgtDigitalizacion, archivo_uuid) is not None:
                        anomalias.append(archivo_url)
                        continue

                    # Tomar los datos del expediente del DgtEntrega que fue copiado con este UUID
                    dgt_entrega = (
                        session.execute(
                            select(DgtEntrega).where(DgtEntrega.archivo_uuid == archivo_uuid).where(DgtEntrega.estatus == "A")
                        )
                        .scalars()
                        .first()
                    )
                    if dgt_entrega is not None and not dgt_entrega.es_anomalo:
                        expediente = dgt_entrega.expediente
                        expediente_anio = dgt_entrega.expediente_anio
                        expediente_num = dgt_entrega.expediente_num
                        descripcion = dgt_entrega.descripcion
                        es_anomalo = False
                    else:
                        expediente = ""
                        expediente_anio = 0
                        expediente_num = 0
                        descripcion = None
                        es_anomalo = True

                    creados.append(archivo_url)
                    if es_anomalo:
                        anomalias.append(archivo_url)
                    if probar:
                        continue
                    dgt_digitalizacion = DgtDigitalizacion(
                        id=archivo_uuid,
                        autoridad_id=autoridad_id,
                        dgt_ruta_id=dgt_ruta.id,
                        archivo_nombre=archivo_nombre,
                        archivo_url=archivo_url,
                        archivo_public_url=blob.public_url,
                        archivo_md5=archivo_md5,
                        archivo_crc32c=archivo_crc32c,
                        archivo_actualizado=archivo_actualizado,
                        archivo_tamano=archivo_tamano,
                        expediente=expediente,
                        expediente_anio=expediente_anio,
                        expediente_num=expediente_num,
                        descripcion=descripcion,
                        es_anomalo=es_anomalo,
                        ultimo_evento="CREADO",
                        ultimo_evento_creado=archivo_actualizado,
                    )
                    session.add(dgt_digitalizacion)
                    session.flush()
                    _agregar_bitacora_al_obtener(session, dgt_digitalizacion, "CREADO")
                    continue

                # B) Ya existe, coinciden el md5 y el crc32c y no fue eliminado, omitir
                if (
                    dgt_digitalizacion.archivo_md5 == archivo_md5
                    and dgt_digitalizacion.archivo_crc32c == archivo_crc32c
                    and dgt_digitalizacion.ultimo_evento != "ELIMINADO"
                ):
                    omitidos += 1
                    continue

                # C) Ya existe pero cambió (o reapareció tras ser eliminado), actualizar con el evento MODIFICADO
                modificados.append(archivo_url)
                if probar:
                    continue
                md5_old = dgt_digitalizacion.archivo_md5
                crc32c_old = dgt_digitalizacion.archivo_crc32c
                dgt_digitalizacion.archivo_nombre = archivo_nombre
                dgt_digitalizacion.archivo_url = archivo_url
                dgt_digitalizacion.archivo_public_url = blob.public_url
                dgt_digitalizacion.archivo_md5 = archivo_md5
                dgt_digitalizacion.archivo_crc32c = archivo_crc32c
                dgt_digitalizacion.archivo_actualizado = archivo_actualizado
                dgt_digitalizacion.archivo_tamano = archivo_tamano
                dgt_digitalizacion.ultimo_evento = "MODIFICADO"
                dgt_digitalizacion.ultimo_evento_creado = archivo_actualizado
                _agregar_bitacora_al_obtener(session, dgt_digitalizacion, "MODIFICADO", md5_old, crc32c_old)

        # D) Están en la base de datos como CREADO o MODIFICADO pero ya no en el depósito, actualizar con el evento ELIMINADO
        for archivo_uuid, dgt_digitalizacion in dgt_digitalizaciones.items():
            if archivo_uuid in archivo_uuids_en_deposito or dgt_digitalizacion.ultimo_evento not in ("CREADO", "MODIFICADO"):
                continue
            eliminados.append(dgt_digitalizacion.archivo_url)
            if probar:
                continue
            dgt_digitalizacion.ultimo_evento = "ELIMINADO"
            dgt_digitalizacion.ultimo_evento_creado = datetime.now(tz=pytz.UTC)
            _agregar_bitacora_al_obtener(
                session, dgt_digitalizacion, "ELIMINADO", dgt_digitalizacion.archivo_md5, dgt_digitalizacion.archivo_crc32c
            )

    # Mostrar los listados y los contadores
    prueba = "[yellow](PRUEBA)[/yellow] " if probar else ""
    prueba_log = "(PRUEBA) " if probar else ""
    for invalido in invalidos:
        bitacora.warning(f"{prueba_log}Inválido: {invalido}")
        console.print(f"{prueba}Inválido: [magenta]{invalido}[/magenta]")
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
        f"Anomalías: {len(anomalias)}, Inválidos: {len(invalidos)}, Omitidos: {omitidos}"
    )
    bitacora.info(f"{prueba_log}{resumen}")
    console.print(
        f"{prueba}Creados: [green]{len(creados)}[/green], Modificados: [yellow]{len(modificados)}[/yellow], "
        f"Eliminados: [red]{len(eliminados)}[/red], Anomalías: [cyan]{len(anomalias)}[/cyan], "
        f"Inválidos: [magenta]{len(invalidos)}[/magenta], Omitidos: {omitidos}"
    )


@app.command()
def obtener(
    dgt_deposito_clave: str | None = None,
    dgt_ruta_clave: str | None = None,
    probar: Annotated[bool, Option("--probar", "-p", help="Probar sin guardar en la base de datos")] = False,
):
    """Insertar o actualizar digitalizaciones a partir de los archivos en los depósitos

    Si proporciona la clave del depósito, se procesan todas las rutas (no eliminadas) del mismo.
    Si proporciona la clave de la ruta, se procesa sólo esa ruta.
    Si ninguna de las anteriores se da, se procesan todas las rutas (no eliminadas) de los depósitos.
    Siempre procesa depósitos con propósito DIGITALIZACIONES.
    """
    console = Console()

    # Bitácora en un archivo log
    settings = get_settings()
    tz = pytz.timezone(settings.TZ)
    ahora = datetime.now(tz=tz)
    archivo_log = f"logs/dgt-digitalizaciones-{ahora.strftime('%Y-%m-%d-%H%M%S')}-obtener.log"
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


def _entregar_dgt_ruta(
    console: Console,
    bitacora: logging.Logger,
    dgt_ruta_id,
    limit: int,
    timeout: int,
    tz,
    probar: bool,
):
    """Enviar a la Plataforma las digitalizaciones de una ruta que no han sido entregadas"""
    with session_scope() as session:
        dgt_ruta = session.get(DgtRuta, dgt_ruta_id)
        bitacora.info(f"Entregando digitalizaciones de {dgt_ruta.clave}...")
        console.print(f"Entregando digitalizaciones de [cyan]{dgt_ruta.clave}[/cyan]...")

        # Inicializar contadores
        enviados = insertados = omitidos = recibidos = 0

        # Consultar los DgtDigitalizacion de la ruta, omitiendo los entregados, los anómalos y los eliminados
        dgt_digitalizaciones = (
            session.execute(
                select(DgtDigitalizacion)
                .where(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id)
                .where(DgtDigitalizacion.entregado.is_(None))
                .where(DgtDigitalizacion.es_anomalo == False)
                .where(DgtDigitalizacion.ultimo_evento != "ELIMINADO")
                .where(DgtDigitalizacion.estatus == "A")
                .order_by(DgtDigitalizacion.expediente_anio, DgtDigitalizacion.expediente_num)
            )
            .scalars()
            .all()
        )
        digitalizaciones_total = len(dgt_digitalizaciones)
        if digitalizaciones_total == 0:
            bitacora.info(f"No hay digitalizaciones por entregar en {dgt_ruta.clave}")
            console.print("No hay digitalizaciones por entregar")
            return

        # Consultar la plataforma y su endpoint para insertar a partir de la autoridad de la ruta
        plataforma = session.execute(
            select(
                DgtPlataforma.api_key, DgtPlataformaEndpoint.id.label("dgt_plataforma_endpoint_id"), DgtPlataformaEndpoint.ruta
            )
            .select_from(Autoridad)
            .join(DgtPlataformaAutoridad, DgtPlataformaAutoridad.autoridad_id == Autoridad.id)
            .join(DgtPlataforma, DgtPlataformaAutoridad.dgt_plataforma_id == DgtPlataforma.id)
            .join(DgtPlataformaEndpoint, DgtPlataformaEndpoint.dgt_plataforma_id == DgtPlataforma.id)
            .where(Autoridad.clave == dgt_ruta.autoridad_clave)
            .where(DgtPlataformaAutoridad.estatus == "A")
            .where(DgtPlataforma.estatus == "A")
            .where(DgtPlataformaEndpoint.proposito == "INSERTAR")
            .where(DgtPlataformaEndpoint.metodo == "POST")
            .where(DgtPlataformaEndpoint.estatus == "A")
        ).first()
        if plataforma is None:
            mensaje = f"Se omite {dgt_ruta.clave} porque la autoridad {dgt_ruta.autoridad_clave} no tiene plataforma con endpoint INSERTAR"
            bitacora.warning(mensaje)
            console.print(f"[yellow]{mensaje}[/yellow]")
            return

        # Barra de progreso
        with Progress() as progress:
            task = progress.add_task("Entregando digitalizaciones:", total=digitalizaciones_total)

            # Bucle por payloads
            for offset in range(0, digitalizaciones_total, limit):
                paquete = dgt_digitalizaciones[offset : offset + limit]
                tope = offset + len(paquete)
                bucle_str = f"Desde {offset} hasta {tope} de {digitalizaciones_total}"
                progress.update(task, advance=len(paquete))

                # Armar el payload
                listado = []
                for item in paquete:
                    listado.append(
                        {
                            "autoridadClave": dgt_ruta.autoridad_clave,
                            "numeroExpediente": item.expediente,
                            "url": item.archivo_public_url,
                        }
                    )
                payload = {"digitalizaciones": listado}
                enviados += len(listado)
                if probar:
                    bitacora.info(f"{bucle_str}: Se enviarían {len(listado)} a {plataforma.ruta}")
                    continue

                # Enviar a la Plataforma, si falla se deja de procesar esta ruta
                try:
                    respuesta = requests.post(
                        url=plataforma.ruta,
                        json=payload,
                        headers={"X-Api-Key": plataforma.api_key},
                        timeout=timeout,
                    )
                    respuesta.raise_for_status()
                except requests.exceptions.ConnectionError:
                    bitacora.error(f"{bucle_str}: No hubo respuesta al tratar de enviar")
                    break
                except requests.exceptions.HTTPError as error:
                    bitacora.error(f"{bucle_str}: Error de estado: {error.response}")
                    break
                except requests.exceptions.RequestException:
                    bitacora.error(f"{bucle_str}: Error desconocido al tratar de enviar")
                    break
                try:
                    datos = respuesta.json()
                except requests.exceptions.JSONDecodeError:
                    bitacora.error(f"{bucle_str}: La respuesta no es JSON")
                    break
                if "success" not in datos:
                    bitacora.error(f"{bucle_str}: La respuesta no tiene success")
                    break

                # Si el success es falso, guardar en la bitácora y pasar al siguiente paquete
                # NOTA: Cuando no hay recibidos el success es falso
                if datos["success"] is not True:
                    bitacora.warning(f"{bucle_str}: Success es falso: {datos.get('message', 'Sin mensaje')}")
                    session.add(
                        DgtPlataformaEndpointBitacora(
                            dgt_plataforma_endpoint_id=plataforma.dgt_plataforma_endpoint_id,
                            payload=payload,
                            respuesta_codigo=respuesta.status_code,
                            respuesta_exitosa=False,
                            respuesta_mensaje=datos.get("message", "Sin mensaje"),
                            respuesta_datos=datos,
                        )
                    )
                    session.commit()
                    continue

                # Acumular los totales de la respuesta
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

                # Juntar los expedientes omitidos, ejemplo: "Expediente no encontrado: SLT-J2-MER 456/2024"
                expedientes_omitidos = set()
                for error in datos.get("errores") or []:
                    if error.startswith("Expediente no encontrado:"):
                        expediente_omitido = re.search(r"\d+/\d+", error)
                        if expediente_omitido:
                            expedientes_omitidos.add(expediente_omitido.group())
                    else:
                        bitacora.error(f"{bucle_str}: Error al enviar: {error}")

                # Guardar en la bitácora los resultados de este paquete
                session.add(
                    DgtPlataformaEndpointBitacora(
                        dgt_plataforma_endpoint_id=plataforma.dgt_plataforma_endpoint_id,
                        payload=payload,
                        respuesta_codigo=respuesta.status_code,
                        respuesta_exitosa=True,
                        respuesta_mensaje=datos.get("message", "Sin mensaje"),
                        respuesta_datos=datos,
                    )
                )

                # Actualizar entregado con el tiempo actual, los omitidos quedan pendientes para el futuro
                ahora = datetime.now(tz=tz)
                for item in paquete:
                    if item.expediente in expedientes_omitidos:
                        bitacora.warning(f"{bucle_str}: Expediente omitido: {item.expediente}")
                    else:
                        item.entregado = ahora

                # Guardar por cada paquete para que la Plataforma y la base de datos no se desincronicen
                session.commit()

    # Mostrar los contadores
    prueba = "[yellow](PRUEBA)[/yellow] " if probar else ""
    prueba_log = "(PRUEBA) " if probar else ""
    bitacora.info(f"{prueba_log}Enviados: {enviados}, Recibidos: {recibidos}, Insertados: {insertados}, Omitidos: {omitidos}")
    console.print(
        f"{prueba}Enviados: [cyan]{enviados}[/cyan], Recibidos: [green]{recibidos}[/green], "
        f"Insertados: [green]{insertados}[/green], Omitidos: [yellow]{omitidos}[/yellow]"
    )


@app.command()
def entregar(
    dgt_deposito_clave: str | None = None,
    dgt_ruta_clave: str | None = None,
    probar: Annotated[bool, Option("--probar", "-p", help="Probar sin enviar ni guardar en la base de datos")] = False,
):
    """Entregar las digitalizaciones a la Plataforma de cada autoridad

    Si proporciona la clave del depósito, se procesan todas las rutas (no eliminadas) del mismo.
    Si proporciona la clave de la ruta, se procesa sólo esa ruta.
    Si ninguna de las anteriores se da, se procesan todas las rutas (no eliminadas) de los depósitos.
    Siempre procesa depósitos con propósito DIGITALIZACIONES.
    """
    console = Console()

    # Bitácora en un archivo log
    settings = get_settings()
    tz = pytz.timezone(settings.TZ)
    ahora = datetime.now(tz=tz)
    archivo_log = f"logs/dgt-digitalizaciones-{ahora.strftime('%Y-%m-%d-%H%M%S')}-entregar.log"
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

    # Procesar cada ruta, cada paquete enviado se guarda en su propia transacción
    for dgt_ruta_id in dgt_rutas_ids:
        _entregar_dgt_ruta(console, bitacora, dgt_ruta_id, settings.LIMIT, settings.TIMEOUT, tz, probar)
