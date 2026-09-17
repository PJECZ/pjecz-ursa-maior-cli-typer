"""
Autoridades commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Exit, Typer

from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.distritos import Distrito
from pjecz_ursa_maior_cli_typer.models.materias import Materia
from pjecz_ursa_maior_cli_typer.utils.database import get_database
from pjecz_ursa_maior_cli_typer.utils.safe_string import safe_clave

app = Typer(help="Autoridades comandos")


@app.command()
def consultar(distrito_clave: str = "", materia_clave: str = "", offset: int = 0, limit: int = 40):
    """Consultar autoridades"""
    console = Console()
    console.print("Consultando autoridades...")
    db = get_database()
    stmt = (
        select(Autoridad.clave, Autoridad.descripcion_corta)
        .filter(Autoridad.estatus == "A")
    )
    distrito_clave = safe_clave(distrito_clave)
    if distrito_clave != "":
        distrito = db.execute(select(Distrito.id).filter(Distrito.clave == distrito_clave)).first()
        if distrito is None:
            console.print(f"[red]Distrito con clave {distrito_clave} no encontrado[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(Autoridad.distrito_id == distrito.id)
    materia_clave = safe_clave(materia_clave)
    if materia_clave != "":
        materia = db.execute(select(Materia.id).filter(Materia.clave == materia_clave)).first()
        if materia is None:
            console.print(f"[red]Materia con clave {materia_clave} no encontrada[/red]")
            raise Exit(code=1)
        stmt = stmt.filter(Autoridad.materia_id == materia.id)
    stmt = stmt.order_by(Autoridad.clave).offset(offset).limit(limit)
    tabla = Table(title="Autoridades")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción corta", header_style="green")
    for item in db.execute(stmt):
        tabla.add_row(item.clave, item.descripcion_corta)
    console.print(tabla)
