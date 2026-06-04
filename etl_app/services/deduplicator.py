"""
services/deduplicator.py — Generación de hashes únicos y detección de duplicados.

Usa SHA-256 para crear identificadores únicos de cada registro.
El hash se basa en los datos normalizados, por lo que detecta
duplicados aunque vengan con distintos formatos en el TXT original.

Funciones públicas:
  - generar_hash_famoso(nombre_norm, fecha_original)    → str (hex 64 chars)
  - generar_hash_lugar(nombre_norm, direccion_completa) → str (hex 64 chars)
  - es_duplicado_famoso(hash_str)                       → bool
  - es_duplicado_lugar(hash_str)                        → bool
"""

import hashlib
import logging

logger = logging.getLogger('etl_app')


# ══════════════════════════════════════════════════════════════
# FUNCIONES DE HASH
# ══════════════════════════════════════════════════════════════

def _calcular_sha256(texto: str) -> str:
    """
    Calcula el SHA-256 de un string normalizado.

    El texto se convierte a minúsculas y se eliminan espacios
    extremos antes de calcular el hash, para que:
    "William Shakespeare" y "william shakespeare" → mismo hash.

    Retorna: string hexadecimal de 64 caracteres.
    """
    texto_normalizado = texto.lower().strip()
    return hashlib.sha256(texto_normalizado.encode('utf-8')).hexdigest()


def generar_hash_famoso(nombre_norm: str, fecha_original: str) -> str:
    """
    Genera un hash único para un registro de Famoso.

    El hash se basa en:
    - nombre_norm:     Nombre normalizado (limpio, sin numeración)
    - fecha_original:  Fecha tal como apareció en el TXT

    Esto asegura que "Albert Einstein - 1879-03-14" y
    "Albert Einstein - 1879/03/14" tengan DISTINTOS hashes
    (son el mismo dato, pero con formato diferente en el TXT).

    Sin embargo, la deduplicación real se hace al comparar
    por nombre + fecha_nacimiento parseada, no solo por hash.

    Estrategia de hash:
        SHA-256(nombre_lower + '|' + fecha_original_lower)

    Ejemplo:
        nombre_norm   = "Albert Einstein"
        fecha_original = "1879-03-14"
        → SHA-256("albert einstein|1879-03-14")
    """
    contenido = f"{nombre_norm}|{fecha_original}"
    hash_val = _calcular_sha256(contenido)
    logger.debug(f"[dedup] Hash famoso: {nombre_norm!r} + {fecha_original!r} → {hash_val[:12]}...")
    return hash_val


def generar_hash_lugar(nombre_norm: str, direccion_completa: str) -> str:
    """
    Genera un hash único para un registro de Lugar.

    El hash se basa en:
    - nombre_norm:          Nombre del lugar normalizado
    - direccion_completa:   Dirección completa normalizada

    Esto detecta como MISMO lugar a:
    - "Machu Picchu" + "Machu Picchu 08680, Peru"
    - "Machu Picchu" + "Machu Picchu 08680, Peru"  (duplicado exacto)

    Pero considera DISTINTOS a:
    - "Machu Picchu" + "Machu Picchu 08680, Peru"
    - "Machu Picchu" + "Cusco 08002, Peru"  (mismas coords, distinta dirección)

    Ejemplo:
        nombre_norm        = "Googleplex"
        direccion_completa = "1600 Amphitheatre Parkway, Mountain View, CA 94043, USA"
        → SHA-256("googleplex|1600 amphitheatre parkway, mountain view, ca 94043, usa")
    """
    contenido = f"{nombre_norm}|{direccion_completa}"
    hash_val = _calcular_sha256(contenido)
    logger.debug(f"[dedup] Hash lugar: {nombre_norm!r} → {hash_val[:12]}...")
    return hash_val


# ══════════════════════════════════════════════════════════════
# DETECCIÓN DE DUPLICADOS (consulta a la BD)
# ══════════════════════════════════════════════════════════════

def es_duplicado_famoso(hash_str: str) -> bool:
    """
    Verifica si ya existe un Famoso con el mismo hash en la BD.

    Importación diferida para evitar problemas de inicialización
    de Django en tests o uso standalone.

    Retorna True si el registro ya existe (es duplicado).
    """
    from etl_app.models import Famoso
    existe = Famoso.objects.filter(hash_registro=hash_str).exists()
    if existe:
        logger.debug(f"[dedup] Duplicado famoso detectado: hash {hash_str[:12]}...")
    return existe


def es_duplicado_lugar(hash_str: str) -> bool:
    """
    Verifica si ya existe un Lugar con el mismo hash en la BD.

    Retorna True si el registro ya existe (es duplicado).
    """
    from etl_app.models import Lugar
    existe = Lugar.objects.filter(hash_registro=hash_str).exists()
    if existe:
        logger.debug(f"[dedup] Duplicado lugar detectado: hash {hash_str[:12]}...")
    return existe


def buscar_famoso_por_nombre(nombre_norm: str):
    """
    Verifica si ya existe un Famoso con el mismo nombre normalizado.
    Esta verificación secundaria captura duplicados que representan a la misma
    persona pero pueden tener fechas con distintos formatos o errores en el TXT.

    Si encuentra la persona, retorna el objeto Famoso existente para que el ETL
    pueda decidir si actualizar sus datos (ej. si la nueva fecha es válida y la vieja no).
    Retorna None si no existe.
    """
    from etl_app.models import Famoso

    famoso_existente = Famoso.objects.filter(nombre_completo__iexact=nombre_norm).first()

    if famoso_existente:
        logger.debug(f"[dedup] Duplicado semántico famoso detectado por nombre: {nombre_norm!r}")

    return famoso_existente
