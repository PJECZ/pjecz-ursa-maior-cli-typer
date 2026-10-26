"""
Autoridades commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave
from pjecz_ursa_maior_cli_typer.models.autoridades import Autoridad
from pjecz_ursa_maior_cli_typer.models.distritos import Distrito
from pjecz_ursa_maior_cli_typer.models.materias import Materia

app = Typer(help="Autoridades comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    distrito_clave: str | None = None,
    materia_clave: str | None = None,
    descripcion_corta: str | None = None,
    es_archivo_solicitante: bool | None = None,
    es_cemasc: bool | None = None,
    es_defensoria: bool | None = None,
    es_extinto: bool | None = None,
    es_jurisdiccional: bool | None = None,
    es_notaria: bool | None = None,
    es_organo_especializado: bool | None = None,
    es_revisor_escrituras: bool | None = None,
):
    """Consultar autoridades"""
    console = Console()
    console.print("Consultando autoridades...")

    # Preparar tabla
    tabla = Table(title="Autoridades")
    tabla.add_column("Clave", header_style="green", no_wrap=True)
    tabla.add_column("Descripción corta", header_style="green")
    tabla.add_column("Distrito", header_style="green", no_wrap=True)
    tabla.add_column("Materia", header_style="green", no_wrap=True)

    # Cláusulas where
    where_clauses = [Autoridad.estatus == "A"]
    if distrito_clave and (distrito_clave := safe_clave(distrito_clave)):
        where_clauses.append(Distrito.clave == distrito_clave)
    if materia_clave and (materia_clave := safe_clave(materia_clave)):
        where_clauses.append(Materia.clave == materia_clave)
    if descripcion_corta and (descripcion_corta := safe_string(descripcion_corta)):
        where_clauses.append(Autoridad.descripcion_corta.like("%" + descripcion_corta + "%"))
    if es_archivo_solicitante is not None:
        where_clauses.append(Autoridad.es_archivo_solicitante == es_archivo_solicitante)
    if es_cemasc is not None:
        where_clauses.append(Autoridad.es_cemasc == es_cemasc)
    if es_defensoria is not None:
        where_clauses.append(Autoridad.es_defensoria == es_defensoria)
    if es_extinto is not None:
        where_clauses.append(Autoridad.es_extinto == es_extinto)
    if es_jurisdiccional is not None:
        where_clauses.append(Autoridad.es_jurisdiccional == es_jurisdiccional)
    if es_notaria is not None:
        where_clauses.append(Autoridad.es_notaria == es_notaria)
    if es_organo_especializado is not None:
        where_clauses.append(Autoridad.es_organo_especializado == es_organo_especializado)
    if es_revisor_escrituras is not None:
        where_clauses.append(Autoridad.es_revisor_escrituras == es_revisor_escrituras)

    # Sentencia
    stmt = (
        select(
            Autoridad.clave,
            Autoridad.descripcion_corta,
            Distrito.clave.label("distrito_clave"),
            Materia.clave.label("materia_clave"),
        )
        .select_from(Autoridad)
        .join(Distrito, Autoridad.distrito_id == Distrito.id)
        .join(Materia, Autoridad.materia_id == Materia.id)
        .where(*where_clauses)
        .order_by(Autoridad.clave)
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.clave,
                item.descripcion_corta,
                item.distrito_clave,
                item.materia_clave,
            )
    console.print(tabla)
