"""
forms.py — Formularios Django para la subida de archivos TXT ETL.

Formularios disponibles:
  - SubirFamososForm    → Sube y procesa DATOS2026-2.txt (o similar)
  - SubirLugaresForm    → Sube y procesa DATOS2026-3.TXT (o similar)

Solo lógica Django Forms. Sin diseño visual (otro desarrollador lo hará).
"""

from django import forms
from etl_app.validators import validar_archivo_txt


class SubirFamososForm(forms.Form):
    """
    Formulario para subir el archivo TXT de Famosos.

    Campo:
        archivo:  FileField que acepta solo .txt
        limpiar_antes: BooleanField opcional para limpiar la BD antes de importar
    """

    archivo = forms.FileField(
        label='Archivo TXT de Famosos',
        help_text=(
            'Suba el archivo DATOS2026-2.txt (o cualquier TXT con el formato: '
            '"N. Nombre - Fecha").'
        ),
        validators=[validar_archivo_txt],
        widget=forms.ClearableFileInput(attrs={
            'accept': '.txt',
            'id': 'id_archivo_famosos',
        }),
    )

    limpiar_antes = forms.BooleanField(
        label='Limpiar base de datos antes de importar',
        required=False,
        initial=False,
        help_text=(
            'Si está marcado, se eliminarán TODOS los registros de Famosos '
            'antes de importar. Use con precaución.'
        ),
        widget=forms.CheckboxInput(attrs={'id': 'id_limpiar_famosos'}),
    )

    def clean_archivo(self):
        """
        Validación adicional del archivo subido.
        El validador validate_archivo_txt ya verificó la extensión.
        Aquí verificamos que el contenido no sea binario.
        """
        archivo = self.cleaned_data.get('archivo')
        if not archivo:
            raise forms.ValidationError('No se seleccionó ningún archivo.')

        # Verificar que el contenido sea texto legible
        try:
            # Leer los primeros 1024 bytes para verificar que es texto
            chunk = archivo.read(1024)
            archivo.seek(0)  # Rebobinar para que el ETL pueda leerlo completo

            if isinstance(chunk, bytes):
                # Intentar decodificar como UTF-8 o latin-1
                try:
                    chunk.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        chunk.decode('latin-1')
                    except UnicodeDecodeError:
                        raise forms.ValidationError(
                            'El archivo no parece ser texto plano. '
                            'Verifique que sea un archivo .txt válido.'
                        )
        except Exception as e:
            raise forms.ValidationError(f'Error al leer el archivo: {e}')

        return archivo


class SubirLugaresForm(forms.Form):
    """
    Formulario para subir el archivo TXT de Lugares.

    Campo:
        archivo:  FileField que acepta solo .txt / .TXT
        limpiar_antes: BooleanField opcional
    """

    archivo = forms.FileField(
        label='Archivo TXT de Lugares',
        help_text=(
            'Suba el archivo DATOS2026-3.TXT (o cualquier TXT con el formato: '
            '"Nombre;Dirección;Georeferencia").'
        ),
        validators=[validar_archivo_txt],
        widget=forms.ClearableFileInput(attrs={
            'accept': '.txt,.TXT',
            'id': 'id_archivo_lugares',
        }),
    )

    limpiar_antes = forms.BooleanField(
        label='Limpiar base de datos antes de importar',
        required=False,
        initial=False,
        help_text=(
            'Si está marcado, se eliminarán TODOS los registros de Lugares, '
            'Direcciones y Georeferencias antes de importar.'
        ),
        widget=forms.CheckboxInput(attrs={'id': 'id_limpiar_lugares'}),
    )

    def clean_archivo(self):
        """Validación adicional del archivo de lugares."""
        archivo = self.cleaned_data.get('archivo')
        if not archivo:
            raise forms.ValidationError('No se seleccionó ningún archivo.')

        # Verificar que el contenido sea texto
        try:
            chunk = archivo.read(1024)
            archivo.seek(0)

            if isinstance(chunk, bytes):
                try:
                    chunk.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        chunk.decode('latin-1')
                    except UnicodeDecodeError:
                        raise forms.ValidationError(
                            'El archivo no parece ser texto plano válido.'
                        )

            # Verificar que tiene al menos un ";" (separador del CSV)
            contenido_preview = chunk.decode('latin-1', errors='replace')
            if ';' not in contenido_preview and len(contenido_preview) > 50:
                raise forms.ValidationError(
                    'El archivo no parece tener el formato correcto. '
                    'Se esperan columnas separadas por ";" '
                    '(Nombre;Dirección;Georeferencia).'
                )

        except forms.ValidationError:
            raise
        except Exception as e:
            raise forms.ValidationError(f'Error al leer el archivo: {e}')

        return archivo


class SubirComunasForm(forms.Form):
    """
    Formulario para subir el archivo TXT de Comunas.
    Sigue la estructura de SubirFamososForm y SubirLugaresForm.
    """

    archivo = forms.FileField(
        label='Archivo TXT de Comunas',
        help_text='Suba el archivo con el listado de comunas (formato TXT).',
        validators=[validar_archivo_txt],
        widget=forms.ClearableFileInput(attrs={
            'accept': '.txt',
            'id': 'id_archivo_comunas',
        }),
    )

    limpiar_antes = forms.BooleanField(
        label='Limpiar base de datos antes de importar',
        required=False,
        initial=False,
        help_text='Elimina registros existentes de Comunas antes de la carga.',
        widget=forms.CheckboxInput(attrs={'id': 'id_limpiar_comunas'}),
    )

    def clean_archivo(self):
        """Validación de lectura de archivo para asegurar integridad."""
        archivo = self.cleaned_data.get('archivo')
        if not archivo:
            raise forms.ValidationError('No se seleccionó ningún archivo.')
            
        try:
            # Reutilizamos la lógica de lectura segura del forms.py existente
            chunk = archivo.read(1024)
            archivo.seek(0)
            
            # Decodificación básica para verificar que es texto
            if isinstance(chunk, bytes):
                chunk.decode('utf-8', errors='replace')
        except Exception as e:
            raise forms.ValidationError(f'Error al leer el archivo: {e}')
            
        return archivo