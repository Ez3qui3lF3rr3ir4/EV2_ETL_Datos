"""
services/validators.py — Validadores de negocio para el ETL.

Diferencia con etl_app/validators.py:
  - Este módulo valida DATOS (registros durante el ETL)
  - etl_app/validators.py valida FORMULARIOS Django (archivos subidos)

Funciones públicas:
  - validar_nombre(nombre)                    → (es_valido:bool, mensaje:str)
  - validar_coordenadas(lat, lon)             → (es_valido:bool, mensaje:str)
  - validar_fecha_nacimiento(fecha)           → (es_valido:bool, mensaje:str)
  - validar_linea_famoso(parsed_data)         → (es_valido:bool, lista_mensajes)
  - validar_linea_lugar(parsed_data)          → (es_valido:bool, lista_mensajes)
"""

import logging
from datetime import date
from decimal import Decimal

logger = logging.getLogger('etl_app')


# ══════════════════════════════════════════════════════════════
# VALIDADORES ATÓMICOS
# ══════════════════════════════════════════════════════════════

def validar_nombre(nombre: str) -> tuple:
    """
    Valida que un nombre no sea vacío ni demasiado corto.

    Retorna: (True, '') si es válido
             (False, mensaje) si no lo es
    """
    if not nombre or not nombre.strip():
        return False, "El nombre está vacío."

    nombre_limpio = nombre.strip()

    if len(nombre_limpio) < 2:
        return False, f"El nombre es demasiado corto: {nombre_limpio!r}"

    if len(nombre_limpio) > 200:
        return False, f"El nombre excede 200 caracteres: {nombre_limpio[:50]}..."

    # Detectar si el nombre es solo números (probablemente un parsing erróneo)
    if nombre_limpio.isdigit():
        return False, f"El nombre parece ser solo números: {nombre_limpio!r}"

    return True, ''


def validar_coordenadas(lat, lon) -> tuple:
    """
    Valida que las coordenadas estén dentro de rangos geográficos válidos.

    lat: Decimal o float — debe estar entre -90 y 90
    lon: Decimal o float — debe estar entre -180 y 180

    Retorna: (True, '') si son válidas
             (False, mensaje) si no lo son
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError) as e:
        return False, f"Coordenadas no son numéricas: {lat}, {lon} — {e}"

    if not (-90.0 <= lat_f <= 90.0):
        return False, f"Latitud fuera de rango [-90, 90]: {lat_f}"

    if not (-180.0 <= lon_f <= 180.0):
        return False, f"Longitud fuera de rango [-180, 180]: {lon_f}"

    return True, ''


def validar_fecha_nacimiento(fecha: date | None, es_aproximada: bool = False) -> tuple:
    """
    Valida que una fecha de nacimiento sea coherente.

    Reglas:
    - Si es_aproximada=True, siempre es válida (se guarda sin fecha_nacimiento)
    - Si es fecha real, debe ser anterior a hoy
    - No debe ser fecha futura

    Retorna: (True, '') si es válida
             (False, mensaje) si no lo es
    """
    if es_aproximada or fecha is None:
        # Las fechas aproximadas son válidas por definición
        return True, ''

    hoy = date.today()

    if fecha > hoy:
        return False, f"La fecha de nacimiento {fecha} es en el futuro."

    # Fechas muy antiguas pero válidas (antes del año 1400) son raras
    # pero posibles (ej: Genghis Khan 1162, aunque este dataset las marca como aproximadas)
    if fecha.year < 1400:
        logger.warning(f"[validator] Fecha muy antigua pero aceptada: {fecha}")

    return True, ''


# ══════════════════════════════════════════════════════════════
# VALIDADORES COMPUESTOS
# ══════════════════════════════════════════════════════════════

def validar_linea_famoso(parsed_data: dict) -> tuple:
    """
    Valida los datos parseados de una línea de famosos ANTES de
    pasarlos al normalizador y guardador.

    parsed_data: dict con keys 'numero', 'nombre_raw', 'fecha_raw'

    Retorna: (es_valido:bool, errores:list[str])
    """
    errores = []

    # Validar que parsed_data no sea None
    if not parsed_data:
        return False, ["Datos parseados vacíos o None."]

    nombre_raw = parsed_data.get('nombre_raw', '')
    fecha_raw = parsed_data.get('fecha_raw', '')

    # Validar nombre
    nombre_valido, msg_nombre = validar_nombre(nombre_raw)
    if not nombre_valido:
        errores.append(f"Nombre inválido: {msg_nombre}")

    # La fecha_raw puede ser cualquier texto (incluido "alrededor de...")
    # Solo validamos que no sea completamente vacía
    if not fecha_raw or not fecha_raw.strip():
        errores.append("La fecha está vacía.")

    es_valido = len(errores) == 0
    return es_valido, errores


def validar_linea_lugar(parsed_data: dict) -> tuple:
    """
    Valida los datos parseados de una línea de lugares ANTES de
    normalizarlos y guardarlos.

    parsed_data: dict con keys 'nombre_raw', 'direccion_raw', 'georef_raw'

    Retorna: (es_valido:bool, errores:list[str])
    """
    errores = []
    advertencias = []

    if not parsed_data:
        return False, ["Datos parseados vacíos o None."]

    nombre_raw = parsed_data.get('nombre_raw', '')
    direccion_raw = parsed_data.get('direccion_raw', '')
    georef_raw = parsed_data.get('georef_raw', '')

    # Validar nombre
    nombre_valido, msg_nombre = validar_nombre(nombre_raw)
    if not nombre_valido:
        errores.append(f"Nombre inválido: {msg_nombre}")

    # La dirección puede estar incompleta pero no debe ser completamente vacía
    if not direccion_raw or not direccion_raw.strip():
        advertencias.append("Dirección vacía (se guardará en blanco).")
        logger.warning(f"[validator] Lugar sin dirección: {nombre_raw!r}")

    # La georeferencia es requerida para ser útil, pero no bloquea el registro
    if not georef_raw or not georef_raw.strip():
        advertencias.append("Georeferencia vacía (no se creará registro de coordenadas).")
        logger.warning(f"[validator] Lugar sin georef: {nombre_raw!r}")

    es_valido = len(errores) == 0
    return es_valido, errores


def validar_extension_txt(nombre_archivo: str) -> tuple:
    """
    Valida que el archivo subido tenga extensión .txt o .TXT.

    Retorna: (True, '') o (False, mensaje_error)
    """
    if not nombre_archivo:
        return False, "No se especificó nombre de archivo."

    extension = nombre_archivo.lower().split('.')[-1] if '.' in nombre_archivo else ''

    if extension != 'txt':
        return False, f"El archivo debe ser .txt, no .{extension}"

    return True, ''
