"""
services/parsers.py — Parsers de líneas crudas para los datasets TXT.

Responsabilidad única: leer una línea de texto y extraer sus campos.
NO normaliza ni valida — eso lo hacen normalizers.py y validators.py.

Funciones públicas:
  - parse_linea_famoso(linea)   → dict con {numero, nombre_raw, fecha_raw} o None
  - parse_linea_lugar(linea)    → dict con {nombre_raw, direccion_raw, georef_raw} o None
"""

import re
import logging

logger = logging.getLogger('etl_app')


# ══════════════════════════════════════════════════════════════
# PARSER — DATASET FAMOSOS (DATOS2026-2.txt)
# ══════════════════════════════════════════════════════════════

# Patrón: "N. Nombre - fecha" donde N es el número de línea
# Captura:
#   grupo 1: número (puede ser texto pegado como "1.")
#   grupo 2: nombre (todo antes del último " - ")
#   grupo 3: fecha (todo después del último " - ")
_RE_FAMOSO = re.compile(
    r'^\s*(\d+)\.\s+(.+?)\s+-\s+(.+)\s*$',
    re.UNICODE
)

# Patrón alternativo: sin número (por si acaso)
_RE_FAMOSO_SIN_NUM = re.compile(
    r'^\s*(.+?)\s+-\s+(.+)\s*$',
    re.UNICODE
)


def parse_linea_famoso(linea: str) -> dict | None:
    """
    Parsea una línea del archivo DATOS2026-2.txt y extrae sus campos.

    Formato esperado:
        "N. Nombre Apellido - fecha"

    Ejemplos:
        "1. William Shakespeare - 1564/04/23"
        "56. Amelia Earhart - 24-07-1897"
        "3. Cleopatra - alrededor del 69 a.C."

    Retorna:
        dict: {
            'numero': int,         Número de línea del TXT
            'nombre_raw': str,     Nombre tal como aparece en el archivo
            'fecha_raw': str,      Fecha tal como aparece en el archivo
        }
        None si la línea no puede ser parseada (vacía, header, etc.)
    """
    if not linea or not linea.strip():
        return None

    linea = linea.strip()

    # Intentar patrón con número
    match = _RE_FAMOSO.match(linea)
    if match:
        numero_str, nombre_raw, fecha_raw = match.groups()
        return {
            'numero': int(numero_str),
            'nombre_raw': nombre_raw.strip(),
            'fecha_raw': fecha_raw.strip(),
        }

    # Casos especiales: si la fecha contiene " - " también (rarísimo, pero seguro)
    # Buscar el ÚLTIMO " - " para separar nombre de fecha
    if ' - ' in linea:
        # Detectar si empieza con número
        num_match = re.match(r'^\s*(\d+)\.\s+', linea)
        if num_match:
            numero = int(num_match.group(1))
            resto = linea[num_match.end():]
        else:
            numero = 0
            resto = linea

        ultimo_sep = resto.rfind(' - ')
        if ultimo_sep != -1:
            nombre_raw = resto[:ultimo_sep].strip()
            fecha_raw = resto[ultimo_sep + 3:].strip()
            if nombre_raw and fecha_raw:
                return {
                    'numero': numero,
                    'nombre_raw': nombre_raw,
                    'fecha_raw': fecha_raw,
                }

    logger.debug(f"[parser_famoso] No se pudo parsear la línea: {linea!r}")
    return None


# ══════════════════════════════════════════════════════════════
# PARSER — DATASET LUGARES (DATOS2026-3.TXT)
# ══════════════════════════════════════════════════════════════

# El separador es ";" y hay 3 columnas:
# Nombre del lugar ; Dirección Completa ; Georeferencia
_SEPARADOR_LUGAR = ';'

# Palabras que indican que es la fila de encabezado
_PALABRAS_HEADER = {'nombre', 'direccion', 'dirección', 'georeferencia', 'lugar'}


def es_header_lugares(linea: str) -> bool:
    """
    Detecta si una línea es el encabezado del CSV de lugares.
    El header real es: "Nombre del lugar;Dirección Completa;Georeferencia"
    (puede venir con encoding corrupto).
    """
    linea_lower = linea.lower().strip()
    # Quitar caracteres de encoding corrupto para comparar
    linea_limpia = re.sub(r'[^\w\s;]', '', linea_lower)
    partes = [p.strip() for p in linea_limpia.split(';')]
    if len(partes) < 2:
        return False
    # Si la primera columna contiene "nombre" y "lugar" → es header
    primera = partes[0]
    return 'nombre' in primera and ('lugar' in primera or 'place' in primera)


def parse_linea_lugar(linea: str) -> dict | None:
    """
    Parsea una línea del archivo DATOS2026-3.TXT.

    Formato: "Nombre del lugar;Dirección Completa;Georeferencia"
    Separador: ";"
    Columnas: 3

    Ejemplos:
        "Googleplex;1600 Amphitheatre Parkway, Mountain View, CA 94043, USA;37.422, -122.084"
        "Buckingham Palace;Westminster, London SW1A 1AA, UK;51.5014, -0.1419"

    Retorna:
        dict: {
            'nombre_raw': str,      Nombre del lugar
            'direccion_raw': str,   Dirección completa (puede tener encoding corrupto)
            'georef_raw': str,      Coordenadas como texto "lat, lon"
        }
        None si la línea no puede parsearse o es un header.
    """
    if not linea or not linea.strip():
        return None

    linea = linea.strip()

    # Ignorar encabezado
    if es_header_lugares(linea):
        logger.debug(f"[parser_lugar] Línea de encabezado ignorada: {linea!r}")
        return None

    partes = linea.split(_SEPARADOR_LUGAR)

    if len(partes) < 3:
        logger.debug(f"[parser_lugar] Línea con menos de 3 columnas: {linea!r}")
        return None

    nombre_raw = partes[0].strip()
    direccion_raw = partes[1].strip()
    # La georeferencia es la tercera columna (si hay más ';', las unimos)
    georef_raw = _SEPARADOR_LUGAR.join(partes[2:]).strip()

    if not nombre_raw:
        logger.debug(f"[parser_lugar] Nombre vacío en línea: {linea!r}")
        return None

    return {
        'nombre_raw': nombre_raw,
        'direccion_raw': direccion_raw,
        'georef_raw': georef_raw,
    }
