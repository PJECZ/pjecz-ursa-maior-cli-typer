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

if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi

figlet Ursa Maior CLI Typer
echo

#
# Para que la cuenta de servicio rclone-guivaloz-hereje@justicia-digital-gob-mx.iam.gserviceaccount.com
# consulte los depósitos en pjecz-gob-mx se agregó en el IAM con los roles tipicos de storage
#
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.google-application-credentials/justicia-digital-gob-mx-guivaloz-en-hereje.json

source .env && export $(sed '/^#/d' .env | cut -d= -f1)
echo "-- Variables de entorno"
echo "   DB_HOST: ${DB_HOST}"
echo "   DB_PORT: ${DB_PORT}"
echo "   DB_NAME: ${DB_NAME}"
echo "   DB_USER: ${DB_USER}"
echo "   DB_PASS: ${DB_PASS}"
echo "   GOOGLE_APPLICATION_CREDENTIALS: ${GOOGLE_APPLICATION_CREDENTIALS}"
echo "   SALT: ${SALT}"
echo "   SQLALCHEMY_DATABASE_URI: ${SQLALCHEMY_DATABASE_URI}"
echo
export PGHOST=$DB_HOST
export PGPORT=$DB_PORT
export PGDATABASE=$DB_NAME
export PGUSER=$DB_USER
export PGPASSWORD=$DB_PASS

echo "-- Python Virtual Environment"
source .venv/bin/activate
echo "   $(python3 --version)"
export PYTHONPATH=$(pwd)
echo "   PYTHONPATH: ${PYTHONPATH}"
echo
alias cli="uv run ${PWD}/pjecz_ursa_maior_cli_typer/app.py"
echo "-- Ejecutar el CLI"
echo "   cli --help"
echo
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

Obtener las entregas

- Rastrea los depósitos de entregas
- Valida el expediente, detectando errores como anomalías
- Inserta o actualiza registros en dgt_entregas

```bash
cli dgt-entregas obtener
```

Obtener las digitalizaciones

- Rastrea los depósitos de digitalizaciones
- Omite las anomalías
- Inserta o actualiza registros en dgt_digitalizaciones

```bash
cli dgt-digitalizaciones
```

Probar la copia de entregas a digitalizaciones

```bash
cli dgt-entregas copiar --probar
```

Revise el archivo `log` en el directorio `./logs` para revisar antes de copiar.

Copiar de entregas a digitalizaciones

```bash
cli dgt-entregas copiar --probar
```

Probar el envío de las digitalizaciones a la Plataforma

```bash
cli dgt-digitalizaciones enviar --probar
```
