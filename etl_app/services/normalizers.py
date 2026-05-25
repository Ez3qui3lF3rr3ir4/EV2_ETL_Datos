"""
services/normalizers.py — Normalización de datos extraídos por los parsers.

Responsabilidad: convertir datos crudos a formatos estándar limpios.

Funciones públicas:
  - normalizar_nombre(texto)            → str (nombre limpio)
  - normalizar_fecha(fecha_raw)         → (date|None, es_aproximada:bool, fecha_formateada:str)
  - normalizar_coordenadas(georef_raw)  → (lat:Decimal, lon:Decimal) | None
  - normalizar_direccion(dir_raw)       → dict con partes de la dirección
  - corregir_encoding(texto)            → str (intenta corregir caracteres corruptos)
"""

import re
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

logger = logging.getLogger('etl_app')

# ══════════════════════════════════════════════════════════════
# NORMALIZACIÓN DE NOMBRES
# ══════════════════════════════════════════════════════════════

def normalizar_nombre(texto: str) -> str:
    """
    Normaliza un nombre de persona o lugar.

    Acciones:
    - Strip de espacios en los extremos
    - Colapsar espacios internos múltiples
    - Eliminar caracteres de control
    - NO cambia capitalización (los nombres históricos son correctos tal cual)

    Ejemplos:
        "  William  Shakespeare  " → "William Shakespeare"
        "MARIE CURIE"             → "MARIE CURIE"  (respeta el original)
    """
    if not texto:
        return ''
    # Quitar caracteres de control
    texto = re.sub(r'[\x00-\x1f\x7f]', '', texto)
    # Colapsar espacios múltiples
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


# ══════════════════════════════════════════════════════════════
# NORMALIZACIÓN DE FECHAS (Dataset Famosos)
# ══════════════════════════════════════════════════════════════

# Formatos de fecha a intentar en orden de prioridad
_FORMATOS_FECHA = [
    '%Y/%m/%d',   # 1564/04/23
    '%Y-%m-%d',   # 1879-03-14
    '%d-%m-%Y',   # 24-07-1897
    '%d/%m/%Y',   # 25/10/1881
]

# Patrones que indican fecha aproximada o histórica no parseable
_RE_APROXIMADA = re.compile(
    r'alrededor\s+de[l]?\s+|circa\s+|approx',
    re.IGNORECASE
)

# Detectar si contiene "a.C." o variantes → fecha antes de Cristo
_RE_AC = re.compile(
    r'a\.?\s*[cC]\.?|BC|before\s+christ|antes\s+de\s+cristo',
    re.IGNORECASE
)

# Patrón especial: "100 a.C./07/12" → tiene a.C. en el año
_RE_AC_CON_FECHA = re.compile(
    r'(\d+)\s*a\.?\s*[cC]\.?[/\-](\d{1,2})[/\-](\d{1,2})',
    re.IGNORECASE
)


def normalizar_fecha(fecha_raw: str) -> tuple:
    """
    Intenta parsear una fecha del dataset de famosos.

    Maneja todos los formatos reales encontrados en DATOS2026-2.txt:
    - YYYY/MM/DD    → 1564/04/23
    - YYYY-MM-DD    → 1879-03-14
    - DD-MM-YYYY    → 24-07-1897
    - DD/MM/YYYY    → 25/10/1881
    - "alrededor de 1162"         → aproximada
    - "alrededor del 69 a.C."     → aproximada
    - "100 a.C./07/12"            → aproximada (contiene a.C.)
    - "356 a.C./07/20"            → aproximada

    Retorna:
        tuple: (
            date | None,          Objeto date si se parseó correctamente, None si no
            bool,                 es_aproximada: True si la fecha no es exacta
            str,                  fecha_formateada: "DD-MM-YYYY" o texto original
        )
    """
    fecha_raw = fecha_raw.strip() if fecha_raw else ''

    if not fecha_raw:
        return None, True, ''

    # ── Caso 1: contiene "alrededor de" → aproximada ──────────
    if _RE_APROXIMADA.search(fecha_raw):
        logger.debug(f"[normalizer] Fecha aproximada detectada: {fecha_raw!r}")
        return None, True, fecha_raw

    # ── Caso 2: contiene "a.C." → fecha antes de Cristo ───────
    if _RE_AC.search(fecha_raw):
        # Intentar extraer el patrón "100 a.C./07/12" aunque sea aproximada
        match_ac = _RE_AC_CON_FECHA.search(fecha_raw)
        if match_ac:
            logger.debug(f"[normalizer] Fecha a.C. con día/mes: {fecha_raw!r}")
        logger.debug(f"[normalizer] Fecha a.C. (histórica): {fecha_raw!r}")
        return None, True, fecha_raw

    # ── Caso 3: intentar todos los formatos conocidos ──────────
    for fmt in _FORMATOS_FECHA:
        try:
            fecha_obj = _parse_fecha_con_formato(fecha_raw, fmt)
            if fecha_obj:
                # Formatear a formato chileno: DD-MM-YYYY
                fecha_formateada = fecha_obj.strftime('%d-%m-%Y')
                logger.debug(f"[normalizer] Fecha parseada: {fecha_raw!r} → {fecha_formateada}")
                return fecha_obj, False, fecha_formateada
        except Exception:
            continue

    # ── Caso 4: no se pudo parsear ─────────────────────────────
    logger.warning(f"[normalizer] Fecha no reconocida: {fecha_raw!r}")
    return None, True, fecha_raw


def _parse_fecha_con_formato(fecha_str: str, fmt: str) -> date | None:
    """
    Intenta parsear una fecha con un formato específico.
    Maneja años históricos (< 1000) con padding de ceros.

    El problema: strptime no maneja bien años de 3 dígitos como "100" con %Y.
    Solución: si el año es < 1900, consideramos que podría ser ambiguo,
    pero para datos históricos válidos (1400-1900) lo aceptamos.
    """
    from datetime import datetime

    try:
        dt = datetime.strptime(fecha_str.strip(), fmt)
        d = dt.date()

        # Validar que el año tenga sentido para fechas d.C.
        # Rechazar años menores a 100 (probablemente a.C. mal escrito)
        if d.year < 100:
            return None

        # Validar mes y día
        if not (1 <= d.month <= 12 and 1 <= d.day <= 31):
            return None

        return d
    except ValueError:
        return None


def formatear_fecha_chilena(fecha: date | None) -> str:
    """
    Convierte un objeto date al formato chileno DD-MM-YYYY.
    Retorna cadena vacía si la fecha es None.
    """
    if not fecha:
        return ''
    return fecha.strftime('%d-%m-%Y')


# ══════════════════════════════════════════════════════════════
# NORMALIZACIÓN DE COORDENADAS (Dataset Lugares)
# ══════════════════════════════════════════════════════════════

# Patrón: "37.422, -122.084" o "37.422,-122.084"
_RE_COORDS = re.compile(
    r'^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$'
)


def normalizar_coordenadas(georef_raw: str) -> tuple | None:
    """
    Parsea una cadena de georeferencia y extrae latitud y longitud.

    Formatos aceptados:
        "37.422, -122.084"
        "-33.8568, 151.2153"
        "41.9029,12.4534"

    Retorna:
        tuple: (Decimal(latitud), Decimal(longitud))
        None si no se puede parsear o las coordenadas son inválidas.
    """
    if not georef_raw or not georef_raw.strip():
        return None

    georef_clean = georef_raw.strip()
    match = _RE_COORDS.match(georef_clean)

    if not match:
        logger.warning(f"[normalizer] Coordenadas no reconocidas: {georef_raw!r}")
        return None

    lat_str, lon_str = match.groups()

    try:
        lat = Decimal(lat_str)
        lon = Decimal(lon_str)
    except InvalidOperation:
        logger.warning(f"[normalizer] Coordenadas inválidas (Decimal): {georef_raw!r}")
        return None

    # Validar rangos geográficos
    if not (-90 <= float(lat) <= 90):
        logger.warning(f"[normalizer] Latitud fuera de rango: {lat}")
        return None

    if not (-180 <= float(lon) <= 180):
        logger.warning(f"[normalizer] Longitud fuera de rango: {lon}")
        return None

    return lat, lon


# ══════════════════════════════════════════════════════════════
# NORMALIZACIÓN DE DIRECCIONES (Dataset Lugares)
# ══════════════════════════════════════════════════════════════

# Tabla de corrección de encoding corrupto (latin-1 mal interpretado como cp1252)
# Los caracteres problemáticos encontrados en el dataset real:
_ENCODING_FIXES = {
    '\xfb': 'ó',   # Direcci\xfbn → Dirección (ó)
    '\xdb': 'ó',   # Variante mayúscula
    '\xdf': 'ss',  # Neuschwansteinstra\xdfe → Neuschwansteinstrasse
    '\xfc': 'ü',   # ü en alemán
    '\xe9': 'é',   # é
    '\xe1': 'á',   # á
    '\xed': 'í',   # í
    '\xf3': 'ó',   # ó
    '\xfa': 'ú',   # ú
    '\xf1': 'ñ',   # ñ
    '\xe0': 'à',   # à (francés)
    '\xe8': 'è',   # è
    '\xef': 'ï',   # ï
    # Carácter especial de ligadura (ﬂ → fl)
    '\ufb02': 'fl',
    '\ufb01': 'fi',
}


def corregir_encoding(texto: str) -> str:
    """
    Intenta corregir caracteres de encoding corrupto en el texto.

    El problema: DATOS2026-3.TXT fue guardado en latin-1 o windows-1252
    pero Python lo lee en UTF-8, causando caracteres como:
    - "Direcci\xfbn" en lugar de "Dirección"
    - "Neuschwansteinstra\xdfe" en lugar de "Neuschwansteinstraße"

    Estrategia:
    1. Intentar re-decodificar si es posible
    2. Aplicar tabla de correcciones conocidas
    3. Usar ftfy si está disponible (no requerido)
    """
    if not texto:
        return ''

    # Estrategia 1: intentar re-encodear como latin-1 y decodificar como utf-8
    try:
        corregido = texto.encode('latin-1').decode('utf-8')
        return corregido
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Estrategia 2: aplicar tabla de correcciones manuales
    resultado = texto
    for char_malo, reemplazo in _ENCODING_FIXES.items():
        resultado = resultado.replace(char_malo, reemplazo)

    return resultado


def normalizar_direccion(dir_raw: str) -> dict:
    """
    Normaliza una dirección completa y la descompone en partes.

    Intenta detectar:
    - nombre_calle: La vía principal (todo antes de la primera coma)
    - numero_calle: Número inicial si existe
    - ciudad_estado_provincia: Ciudad y estado/provincia
    - pais: Último elemento separado por coma (si es país conocido)

    Ejemplo:
        "1600 Amphitheatre Parkway, Mountain View, CA 94043, USA"
        → {
            nombre_calle: "1600 Amphitheatre Parkway",
            numero_calle: "1600",
            ciudad_estado_provincia: "Mountain View, CA 94043",
            pais: "USA",
            direccion_completa: "1600 Amphitheatre Parkway, Mountain View, CA 94043, USA"
        }

    Nota: la descomposición es best-effort. Las direcciones internacionales
    son muy heterogéneas. La dirección_completa siempre es el fallback.
    """
    if not dir_raw:
        return {
            'nombre_calle': '',
            'numero_calle': '',
            'ciudad_estado_provincia': '',
            'pais': '',
            'direccion_completa': '',
        }

    # Corregir encoding primero
    dir_limpia = corregir_encoding(dir_raw).strip()
    # Colapsar espacios múltiples
    dir_limpia = re.sub(r'\s+', ' ', dir_limpia)

    # Separar por comas
    partes = [p.strip() for p in dir_limpia.split(',')]

    nombre_calle = ''
    numero_calle = ''
    ciudad_estado_provincia = ''
    pais = ''

    if len(partes) == 1:
        # Solo hay un elemento, es el nombre de la calle o un lugar especial
        nombre_calle = partes[0]

    elif len(partes) == 2:
        # Ejemplo: "Westminster, London SW1A 1AA, UK" (ya que el resultado de split)
        nombre_calle = partes[0]
        pais = partes[1]

    elif len(partes) >= 3:
        # Asumir: primera parte = calle, última = país, medio = ciudad/estado
        nombre_calle = partes[0]
        pais = partes[-1]
        ciudad_estado_provincia = ', '.join(partes[1:-1])

    # Intentar extraer número del inicio de la calle
    num_match = re.match(r'^(\d+)\s+(.+)$', nombre_calle)
    if num_match:
        numero_calle = num_match.group(1)
        # No modificamos nombre_calle para mantener la dirección completa

    return {
        'nombre_calle': nombre_calle,
        'numero_calle': numero_calle,
        'ciudad_estado_provincia': ciudad_estado_provincia,
        'pais': pais.strip(),
        'direccion_completa': dir_limpia,
    }
