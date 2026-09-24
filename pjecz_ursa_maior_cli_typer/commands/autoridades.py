"""
Autoridades commandos
"""

import json

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.distritos import Distrito
from pjecz_ursa_maior_cli_typer.models.materias import Materia
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = typer.Typer(help="Autoridades comandos")


@app.command()
def consultar(
    distrito_clave: str = "",
    materia_clave: str = "",
    offset: int = 0,
    limit: int = 100,
    como_json: bool = typer.Option(False, "--json", help="Entrega la salida en JSON (para scripts y agentes)"),
):
    """Consultar autoridades"""
    db = get_database()
    stmt = select(Autoridad.clave, Autoridad.descripcion_corta).filter(Autoridad.estatus == "A")
    distrito_clave = safe_clave(distrito_clave)
    if distrito_clave != "":
        distrito = db.execute(select(Distrito.id).filter(Distrito.clave == distrito_clave)).first()
        if distrito is None:
            mensaje = f"Distrito con clave {distrito_clave} no encontrado"
            if como_json:
                resultado = {"success": False, "message": mensaje, "data": [], "total": 0}
                typer.echo(json.dumps(resultado))
                raise typer.Exit(code=1)
            typer.echo(mensaje)
            raise typer.Exit(code=1)
        stmt = stmt.filter(Autoridad.distrito_id == distrito.id)
    materia_clave = safe_clave(materia_clave)
    if materia_clave != "":
        materia = db.execute(select(Materia.id).filter(Materia.clave == materia_clave)).first()
        if materia is None:
            mensaje = f"Materia con clave {materia_clave} no encontrada"
            if como_json:
                resultado = {"success": False, "message": mensaje, "data": [], "total": 0}
                typer.echo(json.dumps(resultado))
                raise typer.Exit(code=1)
            typer.echo(mensaje)
            raise typer.Exit(code=1)
        stmt = stmt.filter(Autoridad.materia_id == materia.id)
    stmt = stmt.order_by(Autoridad.clave).offset(offset).limit(limit)
    if como_json:
        data = []
        for item in db.execute(stmt):
            data.append({"clave": item.clave, "descripcion_corta": item.descripcion_corta})
        resultado = {
            "success": True,
            "message": "Listado de las autoridades activas",
            "data": data,
            "total": len(data),
        }
        typer.echo(json.dumps(resultado))
        return
    console = Console()
    console.print("Consultando autoridades...")
    tabla = Table(title="Autoridades")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción corta", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.descripcion_corta)
    console.print(tabla)
