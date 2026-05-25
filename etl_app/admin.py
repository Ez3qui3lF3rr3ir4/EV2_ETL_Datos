"""
admin.py — Configuración del panel de administración Django para etl_app.

Modelos registrados:
  - FamosoAdmin         → con filtros, búsqueda y ordenamiento
  - LugarAdmin          → con inlines de Direccion y Georeferencia
  - DireccionAdmin      → acceso directo
  - GeoreferenciaAdmin  → acceso directo
  - ErrorImportacionAdmin → con filtros por dataset y tipo
"""

from django.contrib import admin
from django.utils.html import format_html
from etl_app.models import (
    Famoso,
    Lugar,
    Direccion,
    Georeferencia,
    ErrorImportacion,
)


# ══════════════════════════════════════════════════════════════
# INLINES — para mostrar Direccion y Georeferencia dentro de Lugar
# ══════════════════════════════════════════════════════════════

class DireccionInline(admin.StackedInline):
    """Muestra la dirección de un Lugar dentro del mismo formulario de edición."""
    model = Direccion
    extra = 0
    fields = ['nombre_calle', 'numero_calle', 'ciudad_estado_provincia', 'pais', 'direccion_completa']
    readonly_fields = ['direccion_completa']


class GeoreferenciaInline(admin.StackedInline):
    """Muestra las coordenadas de un Lugar dentro del mismo formulario."""
    model = Georeferencia
    extra = 0
    fields = ['latitud', 'longitud']


# ══════════════════════════════════════════════════════════════
# ADMIN — FAMOSOS
# ══════════════════════════════════════════════════════════════

@admin.register(Famoso)
class FamosoAdmin(admin.ModelAdmin):
    """
    Panel de administración para el modelo Famoso.
    """

    # Columnas visibles en la lista
    list_display = [
        'nombre_completo',
        'fecha_nacimiento_formateada',
        'fecha_original',
        'edad_actual',
        'indicador_cumpleanos',
        'indicador_fecha_aproximada',
        'hash_corto',
        'created_at',
    ]

    # Filtros laterales
    list_filter = [
        'esta_de_cumpleanos',
        'es_fecha_aproximada',
        ('fecha_nacimiento', admin.DateFieldListFilter),
    ]

    # Campos de búsqueda
    search_fields = ['nombre_completo', 'fecha_original']

    # Ordenamiento por defecto
    ordering = ['nombre_completo']

    # Campos de solo lectura (calculados automáticamente)
    readonly_fields = [
        'edad_actual',
        'esta_de_cumpleanos',
        'hash_registro',
        'created_at',
        'updated_at',
    ]

    # Agrupar campos en el formulario de edición
    fieldsets = [
        ('Datos del Famoso', {
            'fields': ['nombre_completo', 'fecha_nacimiento', 'fecha_original'],
        }),
        ('Campos Calculados', {
            'fields': ['edad_actual', 'esta_de_cumpleanos'],
            'classes': ['collapse'],
        }),
        ('Control de Calidad', {
            'fields': ['es_fecha_aproximada', 'hash_registro'],
            'classes': ['collapse'],
        }),
        ('Auditoría', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    # ── Columnas personalizadas ──────────────────────────────

    @admin.display(description='Fecha Nacimiento', ordering='fecha_nacimiento')
    def fecha_nacimiento_formateada(self, obj):
        """Muestra la fecha en formato DD-MM-YYYY."""
        if obj.fecha_nacimiento:
            return obj.fecha_nacimiento.strftime('%d-%m-%Y')
        return '—'

    @admin.display(description='🎂 Cumpleaños', boolean=True, ordering='esta_de_cumpleanos')
    def indicador_cumpleanos(self, obj):
        return obj.esta_de_cumpleanos

    @admin.display(description='Fecha Aprox.', boolean=True, ordering='es_fecha_aproximada')
    def indicador_fecha_aproximada(self, obj):
        return obj.es_fecha_aproximada

    @admin.display(description='Hash')
    def hash_corto(self, obj):
        """Muestra solo los primeros 12 caracteres del hash."""
        return obj.hash_registro[:12] + '...' if obj.hash_registro else '—'


# ══════════════════════════════════════════════════════════════
# ADMIN — LUGARES
# ══════════════════════════════════════════════════════════════

@admin.register(Lugar)
class LugarAdmin(admin.ModelAdmin):
    """
    Panel de administración para el modelo Lugar.
    Incluye inlines de Direccion y Georeferencia.
    """

    inlines = [DireccionInline, GeoreferenciaInline]

    list_display = [
        'nombre_lugar',
        'direccion_resumida',
        'coordenadas_resumidas',
        'hash_corto',
        'created_at',
    ]

    search_fields = ['nombre_lugar', 'direccion__pais', 'direccion__ciudad_estado_provincia']

    ordering = ['nombre_lugar']

    readonly_fields = ['hash_registro', 'created_at']

    fieldsets = [
        ('Datos del Lugar', {
            'fields': ['nombre_lugar', 'descripcion'],
        }),
        ('Control de Duplicados', {
            'fields': ['hash_registro'],
            'classes': ['collapse'],
        }),
        ('Auditoría', {
            'fields': ['created_at'],
            'classes': ['collapse'],
        }),
    ]

    @admin.display(description='Dirección')
    def direccion_resumida(self, obj):
        """Muestra la dirección completa truncada."""
        try:
            return obj.direccion.direccion_completa[:60] + '...' \
                if len(obj.direccion.direccion_completa) > 60 \
                else obj.direccion.direccion_completa
        except Direccion.DoesNotExist:
            return '(sin dirección)'

    @admin.display(description='Coordenadas')
    def coordenadas_resumidas(self, obj):
        """Muestra lat, lon con enlace a Google Maps."""
        try:
            lat = obj.georeferencia.latitud
            lon = obj.georeferencia.longitud
            url = f"https://www.google.com/maps?q={lat},{lon}"
            return format_html('<a href="{}" target="_blank">({}, {})</a>', url, lat, lon)
        except Georeferencia.DoesNotExist:
            return '(sin coordenadas)'

    @admin.display(description='Hash')
    def hash_corto(self, obj):
        return obj.hash_registro[:12] + '...' if obj.hash_registro else '—'


# ══════════════════════════════════════════════════════════════
# ADMIN — DIRECCION
# ══════════════════════════════════════════════════════════════

@admin.register(Direccion)
class DireccionAdmin(admin.ModelAdmin):
    """Acceso directo a las direcciones."""

    list_display = ['lugar', 'nombre_calle', 'ciudad_estado_provincia', 'pais']
    search_fields = ['nombre_calle', 'pais', 'ciudad_estado_provincia', 'lugar__nombre_lugar']
    list_filter = ['pais']
    ordering = ['lugar__nombre_lugar']

    raw_id_fields = ['lugar']


# ══════════════════════════════════════════════════════════════
# ADMIN — GEOREFERENCIA
# ══════════════════════════════════════════════════════════════

@admin.register(Georeferencia)
class GeoreferenciaAdmin(admin.ModelAdmin):
    """Acceso directo a las georeferencias."""

    list_display = ['lugar', 'latitud', 'longitud', 'enlace_mapa']
    search_fields = ['lugar__nombre_lugar']
    ordering = ['lugar__nombre_lugar']

    raw_id_fields = ['lugar']

    @admin.display(description='Ver en mapa')
    def enlace_mapa(self, obj):
        url = f"https://www.google.com/maps?q={obj.latitud},{obj.longitud}"
        return format_html('<a href="{}" target="_blank">Google Maps</a>', url)


# ══════════════════════════════════════════════════════════════
# ADMIN — ERRORES DE IMPORTACIÓN
# ══════════════════════════════════════════════════════════════

@admin.register(ErrorImportacion)
class ErrorImportacionAdmin(admin.ModelAdmin):
    """
    Panel de administración para errores ETL.
    Permite auditar qué líneas fallaron y por qué.
    """

    list_display = [
        'dataset',
        'tipo_error',
        'linea_numero',
        'contenido_resumido',
        'mensaje_resumido',
        'created_at',
    ]

    list_filter = [
        'dataset',
        'tipo_error',
        ('created_at', admin.DateFieldListFilter),
    ]

    search_fields = ['contenido_original', 'mensaje_error']

    ordering = ['-created_at', 'dataset', 'linea_numero']

    readonly_fields = ['dataset', 'linea_numero', 'contenido_original',
                       'tipo_error', 'mensaje_error', 'created_at']

    @admin.display(description='Contenido original')
    def contenido_resumido(self, obj):
        return obj.contenido_original[:60] + '...' \
            if len(obj.contenido_original) > 60 \
            else obj.contenido_original

    @admin.display(description='Mensaje de error')
    def mensaje_resumido(self, obj):
        return obj.mensaje_error[:80] + '...' \
            if len(obj.mensaje_error) > 80 \
            else obj.mensaje_error


# ══════════════════════════════════════════════════════════════
# Personalización del sitio de administración
# ══════════════════════════════════════════════════════════════

admin.site.site_header = 'ETL Admin — ArquitecturaDeDatos EV2 P2'
admin.site.site_title = 'ETL Admin'
admin.site.index_title = 'Panel de Administración ETL'
