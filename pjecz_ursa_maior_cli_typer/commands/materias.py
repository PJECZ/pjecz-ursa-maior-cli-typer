"""
Materias commandos
"""

import json

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from pjecz_ursa_maior_cli_typer.models.materias import Materia
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = typer.Typer(help="Materias comandos")


@app.command()
def consultar(como_json: bool = typer.Option(False, "--json", help="Entrega la salida en JSON (para scripts y agentes)")):
    """Consultar materias"""
    db = get_database()
    stmt = select(Materia.clave, Materia.nombre).filter(Materia.estatus == "A").order_by(Materia.clave)
    if como_json:
        data = []
        for item in db.execute(stmt):
            data.append({"clave": item.clave, "nombre": item.nombre})
        resultado = {
            "success": True,
            "message": "Listado de las materias activas",
            "data": data,
            "total": len(data),
        }
        typer.echo(json.dumps(resultado))
        return
    console = Console()
    tabla = Table(title="Materias")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Nombre", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.nombre)
    console.print(tabla)
