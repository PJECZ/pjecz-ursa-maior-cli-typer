"""
DGT Digitalizaciones commandos
"""

import base64
from datetime import datetime
from uuid import UUID

from google.cloud import storage
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.dgt_depositos import DgtDeposito
from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones import DgtDigitalizacion
from pjecz_ursa_maior_cli_typer.models.dgt_digitalizaciones_bitacoras import DgtDigitalizacionBitacora
from pjecz_ursa_maior_cli_typer.models.dgt_entregas import DgtEntrega
from pjecz_ursa_maior_cli_typer.models.dgt_rutas import DgtRuta
from pjecz_ursa_maior_cli_typer.models.vsp_digitalizaciones import VspDigitalizacion
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.digitalizaciones import es_uuid_valido
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="DGT Digitalizaciones comandos")

DGT_DEPOSITO_PROPOSITO = "DIGITALIZACIONES"

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
    stmt = stmt.order_by(DgtDigitalizacion.archivo_actualizado.desc()).offset(offset).limit(limit)
    tabla = Table(title="DGT Digitalizaciones")
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
    console.print(f"Depósito: {dgt_deposito.clave.lower()}, Autoridad: {autoridad.clave}, Directorio: {dgt_ruta.directorio}")

    # Inicializar variables
    archivo_urls_en_deposito = set()
    anomalias = creados = modificados = omitidos = eliminados = invalidos = polizones = 0

    # Obtener los blobs para definir el total de blobs para la barra de progreso
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)
    total = sum(1 for _ in blobs)

    # Obtener de nuevo los blobs para iterar sobre ellos, ya que el anterior generador se agotó al contar
    blobs = cliente.list_blobs(dgt_deposito.clave.lower(), prefix=dgt_ruta.directorio)
    with Progress() as progress:
        task = progress.add_task("Obteniendo digitalizaciones...", total=total)

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
                invalidos += 1
                continue
            archivo_uuid = UUID(archivo_uuid_str)

            # Buscar en dgt_digitalizaciones ese UUID
            dgt_digitalizacion = db.execute(
                select(DgtDigitalizacion)
                .where(DgtDigitalizacion.id == archivo_uuid)
            ).scalar_one_or_none()

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
                if dgt_entrega:
                    expediente = dgt_entrega.expediente if dgt_entrega.expediente else None
                    expediente_anio = dgt_entrega.expediente_anio if 1800 <= dgt_entrega.expediente_anio <= datetime.now().year else None
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
                        expediente_anio = vsp_digitalizacion.expediente_anio if 1800 <= vsp_digitalizacion.expediente_anio <= datetime.now().year else None
                        expediente_num = vsp_digitalizacion.expediente_num if vsp_digitalizacion.expediente_num else None
                        descripcion = vsp_digitalizacion.descripcion if vsp_digitalizacion.descripcion else None
                        ultimo_evento = "CREADO"
                    else:  # No se encontró en ninguno de los dos, entonces este archivo es un polizón
                        polizones += 1
                        continue

                # Si falta expediante, expediente_anio o expediente_num, entonces es una anomalía
                if not expediente or not expediente_anio or not expediente_num:
                    anomalias += 1
                    continue

                # Si su último evento es ELIMINADO
                if ultimo_evento == "ELIMINADO":
                    eliminados += 1

                # Si su último evento es MODIFICADO
                if ultimo_evento == "MODIFICADO":
                    modificados += 1

                # Si su último evento es CREADO
                if ultimo_evento == "CREADO":
                    creados += 1

                # Insertar dgt_digitalizacion
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
                dgt_digitalizacion.es_anomalo = False
                db.add(dgt_digitalizacion)
                continue

            # B.2) Ya existe en dgt_digitalizaciones, si coincide el md5 y crc32c
            if dgt_digitalizacion.archivo_md5 == archivo_md5 and dgt_digitalizacion.archivo_crc32c == archivo_crc32c:
                # TODO: Consultar dgt_entregas para averiguar si fue MODIFICADO o ELIMINADO
                omitidos += 1
                continue

            # C) Hay diferencias en md5 y crc32c, actualizar a MODIFICADO
            archivo_md5_old = dgt_digitalizacion.archivo_md5
            archivo_crc32c_old = dgt_digitalizacion.archivo_crc32c
            dgt_digitalizacion.archivo_md5 = archivo_md5
            dgt_digitalizacion.archivo_crc32c = archivo_crc32c
            dgt_digitalizacion.archivo_actualizado = archivo_actualizado
            dgt_digitalizacion.archivo_tamano = archivo_tamano
            dgt_digitalizacion.ultimo_evento = "MODIFICADO"
            dgt_digitalizacion.ultimo_evento_creado = archivo_actualizado
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

    # D) No están en el depósito, cambiar estatus a "B" y el evento a ELIMINADO
    eliminados = 0
    dgt_digitalizaciones_previas = db.execute(
        select(DgtDigitalizacion)
        .where(DgtDigitalizacion.dgt_ruta_id == dgt_ruta.id)
        .where(DgtDigitalizacion.estatus == "A")
    ).scalars()
    for dgt_digitalizacion in dgt_digitalizaciones_previas:
        if dgt_digitalizacion.archivo_url in archivo_urls_en_deposito:
            continue
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
        eliminados += 1

    # Guardar cambios en la base de datos
    db.commit()

    # Mensajes finales
    if anomalias > 0:
        console.print(f"Anomalías (fueron omitidos): [red]{anomalias}[/red]")
    if creados > 0:
        console.print(f"Creados: [green]{creados}[/green]")
    if modificados > 0:
        console.print(f"Modificados: [yellow]{modificados}[/yellow]")
    if omitidos > 0:
        console.print(f"Omitidos: [gray]{omitidos}[/gray]")
    if eliminados > 0:
        console.print(f"Eliminados: [blue]{eliminados}[/blue]")
    if invalidos > 0:
        console.print(f"Archivos cuyo nombre no es un UUID: [red]{invalidos}[/red]")
    if polizones > 0:
        console.print(f"Archivos están en el depósito pero NO en la BD: [red]{polizones}[/red]")


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
        console.print(f"Obteniendo digitalizaciones de {dgt_ruta_clave}...")
        consulta = consulta.where(DgtRuta.clave == dgt_ruta_clave).where(DgtRuta.estatus == "A")
        renglones = db.execute(consulta).all()
        if not renglones:
            console.print(f"[red]DgtRuta con clave {dgt_ruta_clave} no encontrada o eliminada[/red]")
            raise Exit(code=1)
    else:
        console.print("Obteniendo digitalizaciones de todas las rutas activas...")
        consulta = consulta.where(DgtRuta.estatus == "A")
        renglones = db.execute(consulta).all()
        if not renglones:
            console.print("[yellow]No hay DgtRutas activas[/yellow]")
            raise Exit(code=0)

    cliente = storage.Client()
    for dgt_ruta, dgt_deposito, autoridad in renglones:
        _obtener_dgt_ruta(db, console, cliente, dgt_ruta, dgt_deposito, autoridad)
