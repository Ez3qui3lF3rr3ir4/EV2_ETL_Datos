"""
models.py — Modelos Django para el sistema ETL de ArquitecturaDeDatos EV2 P2.

Modelos:
  - Famoso         → Personas famosas del dataset DATOS2026-2.txt
  - Lugar          → Lugares del dataset DATOS2026-3.TXT
  - Direccion      → Dirección asociada a un Lugar (FK)
  - Georeferencia  → Coordenadas GPS asociadas a un Lugar (FK)
  - ErrorImportacion → Registro de errores durante el proceso ETL
"""

import hashlib
from datetime import date
from django.db import models
from django.utils import timezone


# ══════════════════════════════════════════════════════════════
# DATASET 1 — FAMOSOS (DATOS2026-2.txt)
# ══════════════════════════════════════════════════════════════

class Famoso(models.Model):
    """
    Representa a una persona famosa procesada desde DATOS2026-2.txt.

    El campo hash_registro garantiza que no se inserten duplicados,
    incluso si el mismo registro aparece con distintos formatos de fecha.
    El hash se calcula sobre (nombre_normalizado + fecha_original).
    """

    # ── Datos principales ──────────────────────────────────────
    nombre_completo = models.CharField(
        max_length=200,
        verbose_name='Nombre completo',
        help_text='Nombre normalizado (sin numeración inicial)',
    )

    fecha_nacimiento = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha de nacimiento',
        help_text='Fecha en formato estándar. NULL si la fecha no pudo parsearse.',
    )

    fecha_original = models.CharField(
        max_length=100,
        verbose_name='Fecha original (TXT)',
        help_text='Texto exacto de la fecha tal como apareció en el archivo.',
    )

    # ── Campos calculados ──────────────────────────────────────
    edad_actual = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Edad actual',
        help_text='Calculada automáticamente desde fecha_nacimiento.',
    )

    esta_de_cumpleanos = models.BooleanField(
        default=False,
        verbose_name='¿Está de cumpleaños hoy?',
        help_text='True si hoy coincide con el día y mes de nacimiento.',
    )

    # ── Indicadores de calidad ─────────────────────────────────
    es_fecha_aproximada = models.BooleanField(
        default=False,
        verbose_name='¿Fecha aproximada o histórica?',
        help_text='True si la fecha no pudo parsearse (ej: "alrededor de 1162", "69 a.C.").',
    )

    # ── Control de duplicados ──────────────────────────────────
    hash_registro = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Hash único del registro',
        help_text='SHA-256 calculado sobre nombre_normalizado + fecha_original.',
    )

    # ── Auditoría ──────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        verbose_name = 'Famoso'
        verbose_name_plural = 'Famosos'
        ordering = ['nombre_completo']
        indexes = [
            models.Index(fields=['nombre_completo']),
            models.Index(fields=['fecha_nacimiento']),
            models.Index(fields=['esta_de_cumpleanos']),
        ]

    def __str__(self):
        return f"{self.nombre_completo} ({self.fecha_original})"

    def calcular_edad(self):
        """
        Calcula la edad en años completos desde fecha_nacimiento hasta hoy.
        Retorna None si la fecha no está disponible o es histórica/antigua.
        Solo calcula para fechas d.C. (año >= 1).
        """
        if not self.fecha_nacimiento:
            return None
        hoy = date.today()
        # Proteger contra fechas antes del año 1 (a.C.) — no aplica aquí,
        # pero por seguridad comparamos.
        if self.fecha_nacimiento.year < 1:
            return None
        edad = hoy.year - self.fecha_nacimiento.year
        # Restar 1 si aún no ha llegado el aniversario este año
        if (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day):
            edad -= 1
        return edad

    def calcular_cumpleanos(self):
        """
        Retorna True si hoy es el día y mes de nacimiento del famoso.
        """
        if not self.fecha_nacimiento:
            return False
        hoy = date.today()
        return (hoy.month == self.fecha_nacimiento.month and
                hoy.day == self.fecha_nacimiento.day)

    def save(self, *args, **kwargs):
        """
        Recalcula edad_actual y esta_de_cumpleanos automáticamente en cada guardado.
        """
        self.edad_actual = self.calcular_edad()
        self.esta_de_cumpleanos = self.calcular_cumpleanos()
        super().save(*args, **kwargs)


# ══════════════════════════════════════════════════════════════
# DATASET 2 — LUGARES (DATOS2026-3.TXT)
# ══════════════════════════════════════════════════════════════

class Lugar(models.Model):
    """
    Entidad principal del dataset de lugares.
    Tiene relaciones 1:1 con Direccion y Georeferencia.
    """

    nombre_lugar = models.CharField(
        max_length=200,
        verbose_name='Nombre del lugar',
    )

    descripcion = models.TextField(
        blank=True,
        default='',
        verbose_name='Descripción',
        help_text='Campo reservado para enriquecer el lugar con info adicional.',
    )

    hash_registro = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Hash único',
        help_text='SHA-256 sobre nombre_normalizado + direccion_completa.',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Lugar'
        verbose_name_plural = 'Lugares'
        ordering = ['nombre_lugar']
        indexes = [
            models.Index(fields=['nombre_lugar']),
        ]

    def __str__(self):
        return self.nombre_lugar


class Direccion(models.Model):
    """
    Dirección física asociada a un Lugar.
    El ETL intenta descomponer la dirección completa en partes.
    """

    lugar = models.OneToOneField(
        Lugar,
        on_delete=models.CASCADE,
        related_name='direccion',
        verbose_name='Lugar',
    )

    nombre_calle = models.CharField(
        max_length=300,
        blank=True,
        default='',
        verbose_name='Nombre de la calle / vía',
    )

    numero_calle = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Número',
    )

    ciudad_estado_provincia = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Ciudad / Estado / Provincia',
    )

    pais = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='País',
    )

    direccion_completa = models.TextField(
        verbose_name='Dirección completa (original normalizada)',
    )

    class Meta:
        verbose_name = 'Dirección'
        verbose_name_plural = 'Direcciones'

    def __str__(self):
        return self.direccion_completa[:80]


class Georeferencia(models.Model):
    """
    Coordenadas GPS de un Lugar.
    Latitud y longitud almacenadas con 6 decimales de precisión.
    """

    lugar = models.OneToOneField(
        Lugar,
        on_delete=models.CASCADE,
        related_name='georeferencia',
        verbose_name='Lugar',
    )

    latitud = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        verbose_name='Latitud',
        help_text='Rango válido: -90.0 a 90.0',
    )

    longitud = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        verbose_name='Longitud',
        help_text='Rango válido: -180.0 a 180.0',
    )

    class Meta:
        verbose_name = 'Georeferencia'
        verbose_name_plural = 'Georeferencias'

    def __str__(self):
        return f"({self.latitud}, {self.longitud})"

    def es_valida(self):
        """Verifica que las coordenadas estén dentro de rangos geográficos válidos."""
        return (-90 <= float(self.latitud) <= 90 and
                -180 <= float(self.longitud) <= 180)


# ══════════════════════════════════════════════════════════════
# CONTROL DE CALIDAD — ERRORES DE IMPORTACIÓN
# ══════════════════════════════════════════════════════════════

class ErrorImportacion(models.Model):
    """
    Registra cada línea que falló o generó advertencias durante el ETL.
    Permite auditar el proceso y re-procesar registros problemáticos.
    """

    DATASET_CHOICES = [
        ('famosos', 'Famosos (DATOS2026-2.txt)'),
        ('lugares', 'Lugares (DATOS2026-3.TXT)'),
    ]

    TIPO_ERROR_CHOICES = [
        ('fecha_invalida', 'Fecha inválida o histórica'),
        ('fecha_aproximada', 'Fecha aproximada (alrededor de...)'),
        ('formato_invalido', 'Formato de línea incorrecto'),
        ('coordenada_invalida', 'Coordenada fuera de rango'),
        ('encoding', 'Error de encoding'),
        ('duplicado', 'Registro duplicado'),
        ('otro', 'Otro error'),
    ]

    dataset = models.CharField(
        max_length=20,
        choices=DATASET_CHOICES,
        verbose_name='Dataset de origen',
    )

    linea_numero = models.IntegerField(
        verbose_name='Número de línea',
    )

    contenido_original = models.TextField(
        verbose_name='Contenido original de la línea',
    )

    tipo_error = models.CharField(
        max_length=30,
        choices=TIPO_ERROR_CHOICES,
        default='otro',
        verbose_name='Tipo de error',
    )

    mensaje_error = models.TextField(
        verbose_name='Mensaje de error detallado',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Detectado en',
    )

    class Meta:
        verbose_name = 'Error de importación'
        verbose_name_plural = 'Errores de importación'
        ordering = ['-created_at', 'dataset', 'linea_numero']
        indexes = [
            models.Index(fields=['dataset', 'tipo_error']),
        ]

    def __str__(self):
        return f"[{self.dataset}] Línea {self.linea_numero}: {self.tipo_error}"
