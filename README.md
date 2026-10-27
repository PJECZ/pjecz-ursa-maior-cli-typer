# pjecz-ursa-maior-cli-typer

CLI hecho con Typer para administrar las digitalizaciones.

## Instalación

Crear entorno virtual

```bash
python -m venv .venv
```

Activar entorno virtual

```bashbash
source .venv/bin/activate  # Linux/Mac
```

Instalar dependencias

```bash
uv sync
```

Crear un archivo para las variables de entorno

```bash
cp .env.example .env
```

Crear un archivo `.bashrc` que facilite la carga de las variables de entorno y del entorno Python

```bash
# pjecz-ursa-maior-cli-typer

if [ -f ~/.bashrc ]
then
    . ~/.bashrc
fi

if command -v figlet &> /dev/null
then
    figlet Ursa Maior CLI Typer
else
    echo "== Ursa Maior CLI Typer"
fi
echo

export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.google-application-credentials/service-account.json
if [ -f $GOOGLE_APPLICATION_CREDENTIALS ]
then
    echo "-- Google Application Credentials"
    echo "   ${GOOGLE_APPLICATION_CREDENTIALS}"
    echo
fi

if [ -f .env ]
then
    export $(grep -v '^#' .env | xargs)
    echo "-- Variables de entorno"
    echo "   DB_HOST: ${DB_HOST}"
    echo "   DB_PORT: ${DB_PORT}"
    echo "   DB_NAME: ${DB_NAME}"
    echo "   DB_USER: ${DB_USER}"
    echo "   DB_PASS: ${DB_PASS}"
    echo "   SALT: ${SALT}"
    echo "   SQLALCHEMY_DATABASE_URI: ${SQLALCHEMY_DATABASE_URI}"
    echo "   TZ: ${TZ}"
    echo
fi

if [ -d .venv ]
then
    echo "-- Python Virtual Environment"
    source .venv/bin/activate
    echo "   $(python3 --version)"
    export PYTHONPATH=$(pwd)
    echo "   PYTHONPATH: ${PYTHONPATH}"
    echo
    alias cli="uv run ${PWD}/src/pjecz_ursa_maior_cli_typer/main.py"
    echo "-- Ejecutar el CLI"
    echo "   cli --help"
    echo
fi
```

## Uso

Cargar las variables y el entorno

```bash
source .bashrc
```

Mostrar la ayuda general

```bash
cli --help
```

Consultar las rutas

```bash
cli dgt-rutas consultar
```

Los comandos **obtener**, **copiar** y **enviar** guardan detalles en archivos `logs/*.log`

Obtener las entregas

- Rastrea los depósitos de entregas
- Valida el expediente a partir del nombre del archivo, marcando los errores como anomalías
- Inserta o actualiza registros en dgt_entregas

```bash
cli dgt-entregas obtener
```

Obtener las digitalizaciones

- Rastrea los depósitos de digitalizaciones
- Detecta archivos que no están en la base de datos
- Inserta o actualiza registros en dgt_digitalizaciones

```bash
cli dgt-digitalizaciones obtener
```

Probar la copia de **entregas** a **digitalizaciones**

```bash
cli dgt-entregas copiar --probar
```

Revise el archivo `log` en el directorio `./logs` para revisar antes de copiar.

Copiar de entregas a digitalizaciones

```bash
cli dgt-entregas copiar
```

Probar la entrega de las digitalizaciones a las Plataformas

```bash
cli dgt-digitalizaciones entregar --probar
```

Revise el archivo `log` en el directorio `./logs` para revisar antes de entregar.

Entregar de las digitalizaciones a las Plataformas

```bash
cli dgt-digitalizaciones entregar
```

## Cron

Crear el bash script en `~/.local/bin/cli-dgt-digitalizaciones.sh`

```bash
#!/bin/bash
#
# DGT Digitalizaciones
#

log() {
    echo "$(date '+%Y-%m-%d %H:%M') $*"
}

# Abortar ante cualquier error
set -e

log "Inicia cli-dgt-digitalizaciones.sh"

# Cambiar de directorio
cd $HOME/Documentos/GitHub/PJECZ/pjecz-ursa-maior-cli-typer

# Definir la variable de entorno PYTHONPATH
export PYTHONPATH=$(pwd)

# Exportar la variable de entorno GOOGLE_APPLICATION_CREDENTIALS
export GOOGLE_APPLICATION_CREDENTIALS=/home/pjecz-hercules/.google-application-credentials/justicia-digital-gob-mx-guivaloz-en-hereje.json

# Definir comando uv
CLI="${HOME}/.local/bin/uv run pjecz_ursa_maior_cli_typer/app.py"

#
# PJECZ Ursa Maior CLI Typer
#
# Los siguientes comandos crean archivos log individuales
#

# 0) NO DEBERIA SER NECESARIO Obtener las digitalizaciones, porque se insertan al copiar
$CLI dgt-digitalizaciones obtener

# 1) Obtener las entregas
$CLI dgt-entregas obtener

# 2) Copiar de entregas a digitalizaciones
$CLI dgt-entregas copiar

# 3) Entregar las digitalizaciones a la API de las plataformas
$CLI dgt-digitalizaciones entregar

log "Termina cli-dgt-digitalizaciones.sh"
```

Agregar en el _cron_ la siguiente línea para que se ejecute todos los días en la madrugada a las 03:11

```
11 03 * * * /home/pjecz-hercules/.local/bin/cli-dgt-digitalizaciones.sh >> /dev/null 2>&1
```
