"""
PJECZ Ursa Maior CLI Typer application
"""

import sys

from rich.console import Console
from typer import Typer

from pjecz_ursa_maior_cli_typer.commands.autoridades import app as autoridades_app
from pjecz_ursa_maior_cli_typer.commands.distritos import app as distritos_app
from pjecz_ursa_maior_cli_typer.commands.materias import app as materias_app
from pjecz_ursa_maior_cli_typer.core.exceptions import MyNotValidParamError

app = Typer(help="PJECZ Ursa Maior CLI Typer")
app.add_typer(autoridades_app, name="autoridades")
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
