"""
Distritos commandos
"""

import json

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from pjecz_ursa_maior_cli_typer.models.distritos import Distrito
from pjecz_ursa_maior_cli_typer.utils.database import get_database

app = typer.Typer(help="Distritos comandos")


@app.command()
def consultar(como_json: bool = typer.Option(False, "--json", help="Entrega la salida en JSON (para scripts y agentes)")):
    """Consultar distritos"""
    db = get_database()
    stmt = select(Distrito.clave, Distrito.nombre_corto).filter(Distrito.estatus == "A").order_by(Distrito.clave)
    if como_json:
        data = []
        for item in db.execute(stmt):
            data.append({"clave": item.clave, "nombre_corto": item.nombre_corto})
        resultado = {
            "success": True,
            "message": "Listado de los distritos activos",
            "data": data,
            "total": len(data),
        }
        typer.echo(json.dumps(resultado))
        return
    console = Console()
    tabla = Table(title="Distritos")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Nombre corto", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.nombre_corto)
    console.print(tabla)
