"""
validators.py — Validadores a nivel de formulario Django para etl_app.

Diferencia con services/validators.py:
  - Este módulo valida ARCHIVOS subidos en formularios Django
  - services/validators.py valida datos durante el proceso ETL

Uso en forms.py:
    from etl_app.validators import validar_archivo_txt
    campo = forms.FileField(validators=[validar_archivo_txt])
"""

import os
from django.core.exceptions import ValidationError


def validar_archivo_txt(archivo):
    """
    Validador Django para campos FileField.
    Verifica que el archivo subido sea un .txt y no esté vacío.

    Uso en forms.py:
        archivo = forms.FileField(validators=[validar_archivo_txt])

    Raises:
        ValidationError si el archivo no cumple los requisitos.
    """
    # Verificar extensión
    nombre = archivo.name if hasattr(archivo, 'name') else str(archivo)
    extension = os.path.splitext(nombre)[1].lower()

    if extension not in ['.txt']:
        raise ValidationError(
            f'El archivo debe ser .txt (extensión encontrada: {extension or "ninguna"}). '
            f'Solo se aceptan archivos de texto plano.'
        )

    # Verificar que no esté vacío
    if hasattr(archivo, 'size') and archivo.size == 0:
        raise ValidationError('El archivo está vacío. Suba un archivo TXT con datos.')

    # Verificar tamaño máximo (50 MB)
    max_size = 50 * 1024 * 1024  # 50 MB
    if hasattr(archivo, 'size') and archivo.size > max_size:
        raise ValidationError(
            f'El archivo es demasiado grande ({archivo.size / 1024 / 1024:.1f} MB). '
            f'El tamaño máximo es 50 MB.'
        )


def validar_coordenada_latitud(valor):
    """
    Validador Django para campos de latitud.
    Rango válido: -90 a 90 grados.
    """
    try:
        lat = float(valor)
    except (TypeError, ValueError):
        raise ValidationError(f'La latitud debe ser un número decimal: {valor}')

    if not (-90 <= lat <= 90):
        raise ValidationError(
            f'La latitud {lat} está fuera del rango válido (-90 a 90).'
        )


def validar_coordenada_longitud(valor):
    """
    Validador Django para campos de longitud.
    Rango válido: -180 a 180 grados.
    """
    try:
        lon = float(valor)
    except (TypeError, ValueError):
        raise ValidationError(f'La longitud debe ser un número decimal: {valor}')

    if not (-180 <= lon <= 180):
        raise ValidationError(
            f'La longitud {lon} está fuera del rango válido (-180 a 180).'
        )
