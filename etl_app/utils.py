"""
utils.py — Utilidades generales para etl_app.

Funciones de apoyo que no pertenecen a ningún servicio específico.
"""

import os
import logging
from pathlib import Path
from datetime import date

logger = logging.getLogger('etl_app')


def guardar_archivo_temporal(archivo_django, directorio: str | Path) -> Path:
    """
    Guarda un archivo subido desde un formulario Django en el sistema de archivos.

    Parámetros:
        archivo_django: InMemoryUploadedFile o TemporaryUploadedFile de Django
        directorio:     Directorio donde guardar (ej: settings.MEDIA_ROOT / 'uploads')

    Retorna:
        Path al archivo guardado en disco.

    Ejemplo:
        ruta = guardar_archivo_temporal(form.cleaned_data['archivo'], settings.MEDIA_ROOT)
        resultado = procesar_archivo_famosos(ruta)
    """
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)

    nombre_seguro = Path(archivo_django.name).name  # Evitar path traversal
    ruta_destino = directorio / nombre_seguro

    # Si ya existe un archivo con el mismo nombre, agregar timestamp
    if ruta_destino.exists():
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        stem = Path(nombre_seguro).stem
        ext = Path(nombre_seguro).suffix
        nombre_seguro = f"{stem}_{ts}{ext}"
        ruta_destino = directorio / nombre_seguro

    with open(ruta_destino, 'wb') as f:
        for chunk in archivo_django.chunks():
            f.write(chunk)

    logger.info(f"[utils] Archivo guardado: {ruta_destino}")
    return ruta_destino


def formatear_resultado_para_template(resultado) -> dict:
    """
    Convierte un ResultadoETL o ResultadoETLLugares a un diccionario
    listo para pasar al template Django.

    Retorna dict con:
        - resumen: str con el texto de resumen
        - insertados: int
        - duplicados: int
        - errores: int
        - aproximados: int (solo famosos)
        - lista_errores: lista de dicts
        - lista_duplicados: lista de dicts
        - lista_insertados: lista de dicts
    """
    return {
        'resumen': resultado.resumen(),
        'insertados': resultado.insertados,
        'duplicados': resultado.duplicados,
        'errores': resultado.errores,
        'omitidos': resultado.omitidos,
        'aproximados': getattr(resultado, 'aproximados', 0),
        'sin_coordenadas': getattr(resultado, 'sin_coordenadas', 0),
        'lista_errores': resultado.lista_errores[:50],      # Limitar para la vista
        'lista_duplicados': resultado.lista_duplicados[:50],
        'lista_insertados': resultado.lista_insertados[:50],
    }


def calcular_edad_desde_fecha(fecha_nacimiento: date | None) -> int | None:
    """
    Calcula la edad en años completos desde una fecha de nacimiento hasta hoy.
    Función standalone (no depende de modelos).
    """
    if not fecha_nacimiento:
        return None
    hoy = date.today()
    edad = hoy.year - fecha_nacimiento.year
    if (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        edad -= 1
    return edad


def es_cumpleanos_hoy(fecha_nacimiento: date | None) -> bool:
    """
    Retorna True si la fecha_nacimiento coincide con el día y mes de hoy.
    """
    if not fecha_nacimiento:
        return False
    hoy = date.today()
    return (hoy.month == fecha_nacimiento.month and
            hoy.day == fecha_nacimiento.day)
