"""
DGT Plataformas Endpoints Bitácoras commandos
"""

from datetime import datetime, timedelta
from typing import Annotated

import pytz
from rich.console import Console
from sqlalchemy import delete, func, select
from typer import Option, Typer

from pjecz_ursa_maior_cli_typer.config.settings import get_settings
from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.exceptions import MyNotValidParamError
from pjecz_ursa_maior_cli_typer.models.dgt_plataformas_endpoints_bitacoras import DgtPlataformaEndpointBitacora

app = Typer(help="DGT Plataformas Endpoints Bitácoras comandos")


@app.command()
def eliminar(
    dias: Annotated[int, Option("--dias", "-d", help="Eliminar los registros creados hace más de estos días")] = 7,
    probar: Annotated[bool, Option("--probar", "-p", help="Probar sin eliminar en la base de datos")] = False,
):
    """Eliminar los registros de la bitácora de los endpoints anteriores a los días dados"""
    console = Console()

    # Validar los días
    if dias < 1:
        raise MyNotValidParamError("El parámetro --dias debe ser mayor o igual a 1")

    # Calcular la fecha y hora límite
    settings = get_settings()
    tz = pytz.timezone(settings.TZ)
    limite = datetime.now(tz=tz) - timedelta(days=dias)
    console.print(f"Eliminando bitácoras de endpoints anteriores a [cyan]{limite.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]...")

    with session_scope() as session:
        # Probar: sólo contar los registros que se eliminarían
        if probar:
            cantidad = session.execute(
                select(func.count()).select_from(DgtPlataformaEndpointBitacora).where(DgtPlataformaEndpointBitacora.creado < limite)
            ).scalar_one()
            console.print(f"[yellow](PRUEBA)[/yellow] Se eliminarían [red]{cantidad}[/red] registros")
            return

        # Eliminar, el commit se hace al salir del session_scope
        resultado = session.execute(delete(DgtPlataformaEndpointBitacora).where(DgtPlataformaEndpointBitacora.creado < limite))
        cantidad = resultado.rowcount

    console.print(f"Eliminados: [red]{cantidad}[/red] registros")
