"""
Autoridades commandos
"""

import json

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.distritos import Distrito
from pjecz_ursa_maior_cli_typer.models.materias import Materia
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = typer.Typer(help="Autoridades comandos")


@app.command()
def consultar(
    distrito_clave: str = typer.Option("", help="Filtrar por la clave del distrito"),
    materia_clave: str = typer.Option("", help="Filtrar por la clave de la materia"),
    offset: int = typer.Option(0, help="Offset de la consulta, por defecto es cero"),
    limit: int = typer.Option(50, help="Limit de la consulta, por defcto es 50"),
    como_json: bool = typer.Option(False, "--json", help="Entrega la salida en JSON (para scripts y agentes)"),
):
    """Consultar autoridades"""
    db = get_database()
    stmt = select(Autoridad.clave, Autoridad.descripcion_corta).where(Autoridad.estatus == "A")
    count = select(func.count()).select_from(Autoridad).where(Autoridad.estatus == "A")
    distrito_clave = safe_clave(distrito_clave)
    if distrito_clave != "":
        distrito = db.execute(select(Distrito.id).where(Distrito.clave == distrito_clave)).first()
        if distrito is None:
            mensaje = f"Distrito con clave {distrito_clave} no encontrado"
            if como_json:
                resultado = {"success": False, "message": mensaje, "data": [], "total": 0}
                typer.echo(json.dumps(resultado))
                raise typer.Exit(code=1)
            typer.echo(mensaje)
            raise typer.Exit(code=1)
        stmt = stmt.where(Autoridad.distrito_id == distrito.id)
        count = count.where(Autoridad.distrito_id == distrito.id)
    materia_clave = safe_clave(materia_clave)
    if materia_clave != "":
        materia = db.execute(select(Materia.id).where(Materia.clave == materia_clave)).first()
        if materia is None:
            mensaje = f"Materia con clave {materia_clave} no encontrada"
            if como_json:
                resultado = {"success": False, "message": mensaje, "data": [], "total": 0}
                typer.echo(json.dumps(resultado))
                raise typer.Exit(code=1)
            typer.echo(mensaje)
            raise typer.Exit(code=1)
        stmt = stmt.where(Autoridad.materia_id == materia.id)
        count = count.where(Autoridad.materia_id == materia.id)
    stmt = stmt.order_by(Autoridad.clave)
    if como_json:
        data = []
        for item in db.execute(stmt.offset(offset).limit(limit)):
            data.append({"clave": item.clave, "descripcion_corta": item.descripcion_corta})
        resultado = {
            "success": True,
            "message": "Listado de las autoridades activas",
            "data": data,
            "total": db.scalar(count),
        }
        typer.echo(json.dumps(resultado))
        return
    console = Console()
    console.print("Consultando autoridades...")
    tabla = Table(title=f"{db.scalar(count)} Autoridades")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción corta", header_style="green")
    for item in db.execute(stmt.offset(offset).limit(limit)):
        tabla.add_row(item.clave, item.descripcion_corta)
    console.print(tabla)
