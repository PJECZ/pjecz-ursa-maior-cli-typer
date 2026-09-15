"""
PJECZ Ursa Maior CLI Typer application
"""

from typer import Typer

from pjecz_ursa_maior_cli_typer.commands.autoridades import app as autoridades_app
from pjecz_ursa_maior_cli_typer.commands.dgt_depositos import app as dgt_depositos_app
from pjecz_ursa_maior_cli_typer.commands.dgt_digitalizaciones import app as dgt_digitalizaciones_app
from pjecz_ursa_maior_cli_typer.commands.dgt_digitalizaciones_bitacoras import app as dgt_digitalizaciones_bitacoras_app
from pjecz_ursa_maior_cli_typer.commands.dgt_entregas import app as dgt_entregas_app
from pjecz_ursa_maior_cli_typer.commands.dgt_entregas_bitacoras import app as dgt_entregas_bitacoras_app
from pjecz_ursa_maior_cli_typer.commands.dgt_rutas import app as dgt_rutas_app
from pjecz_ursa_maior_cli_typer.commands.dgt_tipos import app as dgt_tipos_app
from pjecz_ursa_maior_cli_typer.commands.distritos import app as distritos_app
from pjecz_ursa_maior_cli_typer.commands.materias import app as materias_app

app = Typer(help="PJECZ Ursa Maior CLI Typer")
app.add_typer(autoridades_app, name="autoridades")
app.add_typer(dgt_depositos_app, name="dgt_depositos")
app.add_typer(dgt_digitalizaciones_app, name="dgt_digitalizaciones")
app.add_typer(dgt_digitalizaciones_bitacoras_app, name="dgt_digitalizaciones_bitacoras")
app.add_typer(dgt_entregas_app, name="dgt_entregas")
app.add_typer(dgt_entregas_bitacoras_app, name="dgt_entregas_bitacoras")
app.add_typer(dgt_rutas_app, name="dgt_rutas")
app.add_typer(dgt_tipos_app, name="dgt_tipos")
app.add_typer(distritos_app, name="distritos")
app.add_typer(materias_app, name="materias")

if __name__ == "__main__":
    app()
