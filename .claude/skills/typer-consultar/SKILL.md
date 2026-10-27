---
name: typer-consultar
description: Inicia un archivo de comandos Typer en src/pjecz_ursa_maior_cli_typer/commands/ con el subcomando "consultar" que muestra una tabla Rich, siguiendo las convenciones de commands/autoridades.py. Úsalo cuando se pida crear o iniciar un comando "consultar" para un modelo.
argument-hint: 'modelo (ej. dgt_entregas) y opcionalmente los filtros'
allowed-tools: Read, Glob, Grep, Write, Edit, AskUserQuestion, Bash(ls:*), Bash(cat:*)
---

# /typer-consultar — Iniciar comando con subcomando "consultar"

## Contexto de la sesión

Modelos disponibles:
!`ls src/pjecz_ursa_maior_cli_typer/models/`

Comandos que ya existen:
!`ls src/pjecz_ursa_maior_cli_typer/commands/`

---

## Paso 1. Estudiar el modelo

1. Identifica el modelo a partir de `$ARGUMENTS`. Si no viene, pregúntalo.
2. Lee `src/pjecz_ursa_maior_cli_typer/models/<modulo>.py` y anota:
   - Nombre de la clase (ej. `DgtEntrega`) y del módulo (ej. `dgt_entregas`).
   - Columnas y sus tipos (`str`, `bool`, `int`, `date`, `datetime`, etc.).
   - Claves foráneas (`*_id`) y los modelos padres a los que apuntan.
3. Si un padre tiene a su vez otro padre útil para filtrar (ej. `Autoridad` → `Distrito`), tómalo en cuenta.
4. Lee `src/pjecz_ursa_maior_cli_typer/commands/autoridades.py` como referencia de estilo.

## Paso 2. Pedir los filtros y las columnas

Si `$ARGUMENTS` no los trae, pregunta al usuario:

- **Filtros** adicionales a `offset` y `limit` (que SIEMPRE van).
- **Columnas** a mostrar en la tabla (si no las indica, propón: la clave/identificador principal, una descripción o nombre, y las claves de los padres).
- **Orden** (por defecto, la clave del modelo; si no tiene clave, `id` descendente).

No inventes filtros que el usuario no pidió.

## Paso 3. Generar el archivo

Escribe `src/pjecz_ursa_maior_cli_typer/commands/<modulo>.py` con esta estructura exacta. Si el archivo ya existe, avisa antes de sobrescribirlo.

```python
"""
<Plural capitalizado> commandos
"""

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from typer import Typer

from pjecz_ursa_maior_cli_typer.core.database import session_scope
from pjecz_ursa_maior_cli_typer.core.safe_string import safe_clave, safe_string  # sólo los que se usen
from pjecz_ursa_maior_cli_typer.models.<modulo> import <Modelo>
from pjecz_ursa_maior_cli_typer.models.<padre> import <Padre>  # uno por cada join

app = Typer(help="<Plural capitalizado> comandos")


@app.command()
def consultar(
    offset: int = 0,
    limit: int = 25,
    <filtros>,
):
    """Consultar <plural>"""
    console = Console()
    console.print("Consultando <plural>...")

    # Preparar tabla
    tabla = Table(title="<Plural capitalizado>")
    tabla.add_column("<Encabezado>", header_style="green", no_wrap=True)
    ...

    # Cláusulas where
    where_clauses = [<Modelo>.estatus == "A"]
    ...

    # Sentencia
    stmt = (
        select(
            <Modelo>.<columna>,
            <Padre>.clave.label("<padre>_clave"),
        )
        .select_from(<Modelo>)
        .join(<Padre>, <Modelo>.<padre>_id == <Padre>.id)
        .where(*where_clauses)
        .order_by(<Modelo>.clave)
        .offset(offset)
        .limit(limit)
    )

    # Consultar, agregar a la tabla y mostrar
    with session_scope() as session:
        for item in session.execute(stmt).all():
            tabla.add_row(
                item.<columna>,
                item.<padre>_clave,
            )
    console.print(tabla)
```

### Reglas para los filtros

Todos los filtros (salvo `offset` y `limit`) son opcionales con valor por defecto `None`. En la firma van primero los de padres (`<padre>_clave`), luego los de columnas propias en orden alfabético, y al final los booleanos `es_*` en orden alfabético.

| Tipo de filtro | Firma | Cláusula where |
|---|---|---|
| Clave de un padre | `distrito_clave: str \| None = None` | `if distrito_clave and (distrito_clave := safe_clave(distrito_clave)):`<br>`    where_clauses.append(Distrito.clave == distrito_clave)` |
| Clave propia | `clave: str \| None = None` | `if clave and (clave := safe_clave(clave)):`<br>`    where_clauses.append(<Modelo>.clave == clave)` |
| Texto (búsqueda parcial) | `descripcion: str \| None = None` | `if descripcion and (descripcion := safe_string(descripcion)):`<br>`    where_clauses.append(<Modelo>.descripcion.like("%" + descripcion + "%"))` |
| Booleano | `es_activo: bool \| None = None` | `if es_activo is not None:`<br>`    where_clauses.append(<Modelo>.es_activo == es_activo)` |
| Entero / ID de padre | `distrito_id: int \| None = None` | `if distrito_id is not None:`<br>`    where_clauses.append(<Modelo>.distrito_id == distrito_id)` |
| Rango de fechas | `creado_desde: date \| None = None`, `creado_hasta: ...` | `<Modelo>.creado >= creado_desde` / `<Modelo>.creado <= creado_hasta` |

- La primera cláusula siempre es `<Modelo>.estatus == "A"`.
- Todo parámetro `str` se sanitiza antes de usarlo, con el patrón `if x and (x := safe_...(x)):`:
  - Si es una **clave** (`clave`, `*_clave`), pasa por `safe_clave`.
  - Si es cualquier otro **texto** (descripción, nombre, etc.), pasa por `safe_string`.
  - Nunca uses un parámetro `str` en una cláusula sin pasarlo por una de las dos.
- Importa de `core.safe_string` sólo las funciones que uses (`safe_clave`, `safe_string` o ambas).
- Si filtras por un padre, ese padre debe tener su `.join(...)` en la sentencia aunque no se muestre su columna.

### Reglas para la tabla

- Cada columna: `tabla.add_column("<Encabezado en español con acentos>", header_style="green")`. Agrega `no_wrap=True` a claves, fechas, IDs y booleanos; no a descripciones largas.
- Columnas de padres se seleccionan con `.label("<padre>_<columna>")` y se leen como `item.<padre>_<columna>`.
- `tabla.add_row` sólo acepta cadenas: convierte valores no-str (`str(item.id)`, `item.creado.strftime("%Y-%m-%d %H:%M:%S")`, `"Sí" if item.es_x else "No"`).
- El orden de `add_column`, de `select(...)` y de `add_row` debe coincidir.

## Paso 4. Registrar en main.py

En `src/pjecz_ursa_maior_cli_typer/main.py`, si no está ya registrado:

1. Agrega `from pjecz_ursa_maior_cli_typer.commands.<modulo> import app as <modulo>_app` en orden alfabético con los demás imports de `commands`.
2. Agrega `app.add_typer(<modulo>_app, name="<modulo con guiones>")` en orden alfabético (ej. `dgt_entregas` → `name="dgt-entregas"`).

## Paso 5. Resumen

Muestra al usuario los filtros generados, las columnas de la tabla y un ejemplo de uso:

```
uv run pjecz-ursa-maior-cli-typer <modulo-con-guiones> consultar --limit 10 --<filtro> <valor>
```
