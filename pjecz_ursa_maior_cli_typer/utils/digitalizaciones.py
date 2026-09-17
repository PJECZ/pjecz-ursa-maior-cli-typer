"""
Digitalizaciones
"""

import re
from datetime import date


def parsear_num_anio_desc(texto: str) -> tuple[int, int, str]:
    """
    Parsea un texto con formato NNN-YYYY-DDDD (número-año-descripción).

    - numero: entero >= 1 (si no es válido, se entrega como 0)
    - año: entero de 4 dígitos, hasta el año presente (si no es válido, se entrega como 0)
    - descripcion: texto opcional, el resto de la cadena (puede contener guiones)

    Retorna (numero, año, descripcion)
    """
    texto = texto.strip()

    # Se separa en máximo 3 partes: numero, año y el resto (descripción)
    partes = texto.split("-", 2)
    numero_str = partes[0] if len(partes) > 0 else ""
    anio_str = partes[1] if len(partes) > 1 else ""
    descripcion = partes[2].strip() if len(partes) > 2 else ""

    # Sustituir guiones medios internos por espacios
    descripcion = descripcion.replace("-", " ")
    # Normalizar espacios múltiples que pudieran resultar
    descripcion = re.sub(r"\s+", " ", descripcion).strip()

    # Validar número: solo dígitos y >= 1
    numero = 0
    if re.fullmatch(r"\d+", numero_str):
        valor = int(numero_str)
        if valor >= 1:
            numero = valor

    # Validar año: exactamente 4 dígitos y no mayor al año actual
    anio = 0
    if re.fullmatch(r"\d{4}", anio_str):
        valor = int(anio_str)
        if valor <= date.today().year:
            anio = valor

    return numero, anio, descripcion
