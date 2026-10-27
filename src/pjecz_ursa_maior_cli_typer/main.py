"""
PJECZ Ursa Maior CLI Typer application
"""

import sys

from rich.console import Console
from typer import Typer

from pjecz_ursa_maior_cli_typer.commands.autoridades import app as autoridades_app
from pjecz_ursa_maior_cli_typer.commands.dgt_depositos import app as dgt_depositos_app
from pjecz_ursa_maior_cli_typer.commands.dgt_entregas import app as dgt_entregas_app
from pjecz_ursa_maior_cli_typer.commands.dgt_plataformas import app as dgt_plataformas_app
from pjecz_ursa_maior_cli_typer.commands.dgt_plataformas_autoridades import app as dgt_plataformas_autoridades_app
from pjecz_ursa_maior_cli_typer.commands.dgt_plataformas_endpoints import app as dgt_plataformas_endpoints_app
from pjecz_ursa_maior_cli_typer.commands.dgt_rutas import app as dgt_rutas_app
from pjecz_ursa_maior_cli_typer.commands.dgt_tipos import app as dgt_tipos_app
from pjecz_ursa_maior_cli_typer.commands.distritos import app as distritos_app
from pjecz_ursa_maior_cli_typer.commands.materias import app as materias_app
from pjecz_ursa_maior_cli_typer.core.exceptions import MyNotValidParamError

app = Typer(help="PJECZ Ursa Maior CLI Typer")
app.add_typer(autoridades_app, name="autoridades")
app.add_typer(dgt_depositos_app, name="dgt-depositos")
app.add_typer(dgt_entregas_app, name="dgt-entregas")
app.add_typer(dgt_plataformas_app, name="dgt-plataformas")
app.add_typer(dgt_plataformas_autoridades_app, name="dgt-plataformas-autoridades")
app.add_typer(dgt_plataformas_endpoints_app, name="dgt-plataformas-endpoints")
app.add_typer(dgt_rutas_app, name="dgt-rutas")
app.add_typer(dgt_tipos_app, name="dgt-tipos")
app.add_typer(distritos_app, name="distritos")
app.add_typer(materias_app, name="materias")


def main():
    """Ejecutar la aplicación y mostrar los parámetros inválidos sin traceback"""
    try:
        app()
    except MyNotValidParamError as error:
        Console(stderr=True).print(f"[red]{error}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
