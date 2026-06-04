"""
services/lugares_etl.py — ETL completo para el dataset de Lugares (DATOS2026-3.TXT).

Flujo ETL:
  1. Leer TXT con manejo de encoding (latin-1 / utf-8)
  2. Detectar y saltar el header automáticamente
  3. Parsear cada línea separada por ";"
  4. Corregir encoding corrupto (Direcci\xfbn → Dirección)
  5. Normalizar nombre del lugar y dirección
  6. Parsear coordenadas GPS
  7. Validar datos
  8. Generar hash único
  9. Deduplicar (hash exacto)
  10. Crear registros en Lugar + Direccion + Georeferencia
  11. Registrar errores en ErrorImportacion

Función principal:
  - procesar_archivo_lugares(ruta_archivo) → ResultadoETLLugares
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger('etl_app')
logger_errores = logging.getLogger('etl_app.errores')


# ══════════════════════════════════════════════════════════════
# ESTRUCTURA DE RESULTADO
# ══════════════════════════════════════════════════════════════

@dataclass
class ResultadoETLLugares:
    """Resultado del ETL de Lugares."""
    total_lineas: int = 0
    insertados: int = 0
    duplicados: int = 0
    errores: int = 0
    omitidos: int = 0
    sin_coordenadas: int = 0
    lista_insertados: list = field(default_factory=list)
    lista_duplicados: list = field(default_factory=list)
    lista_errores: list = field(default_factory=list)

    def resumen(self) -> str:
        return (
            f"[RESUMEN ETL LUGARES]\n"
            f"  Total líneas procesadas : {self.total_lineas}\n"
            f"  Insertados              : {self.insertados}\n"
            f"  Duplicados (omitidos)   : {self.duplicados}\n"
            f"  Sin coordenadas válidas : {self.sin_coordenadas}\n"
            f"  Errores                 : {self.errores}\n"
            f"  Líneas omitidas         : {self.omitidos}\n"
        )


# ══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL ETL
# ══════════════════════════════════════════════════════════════

def procesar_archivo_lugares(ruta_archivo: str | Path) -> ResultadoETLLugares:
    """
    Ejecuta el proceso ETL completo sobre el archivo de lugares.

    El encoding del archivo real (DATOS2026-3.TXT) es problemático:
    tiene caracteres latin-1 / windows-1252 mezclados con UTF-8.
    Se intenta leer con varios encodings y se aplica corrección manual.

    Parámetros:
        ruta_archivo: Ruta al archivo TXT (DATOS2026-3.TXT)

    Retorna:
        ResultadoETLLugares con estadísticas completas.
    """
    from etl_app.models import EjecucionETL
    from django.utils import timezone

    ruta = Path(ruta_archivo)
    resultado = ResultadoETLLugares()

    ejecucion = EjecucionETL.objects.create(
        dataset='lugares',
        fecha_inicio=timezone.now()
    )

    if not ruta.exists():
        logger.error(f"[ETL Lugares] Archivo no encontrado: {ruta}")
        raise FileNotFoundError(f"Archivo no encontrado: {ruta}")

    logger.info(f"[ETL Lugares] Iniciando procesamiento: {ruta.name}")

    lineas = _leer_archivo_lugares(ruta)
    resultado.total_lineas = len(lineas)
    ejecucion.registros_leidos = len(lineas)
    logger.info(f"[ETL Lugares] Total de líneas a procesar: {len(lineas)}")

    for num_linea, linea in enumerate(lineas, start=1):
        _procesar_linea_lugar(
            linea=linea,
            num_linea=num_linea,
            resultado=resultado,
            ejecucion=ejecucion
        )

    ejecucion.fecha_fin = timezone.now()
    ejecucion.save()
    logger.info(f"[ETL Lugares] Completado. {resultado.resumen()}")
    return resultado


def _leer_archivo_lugares(ruta: Path) -> list:
    """
    Lee el archivo de lugares con manejo robusto de encoding.

    Prioridad de encodings:
    1. utf-8-sig (UTF-8 con BOM)
    2. utf-8
    3. latin-1  ← el más probable para el dataset real
    4. cp1252   ← Windows-1252
    5. fallback con errors='replace'
    """
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']

    for enc in encodings:
        try:
            with open(ruta, 'r', encoding=enc) as f:
                lineas = f.readlines()
            logger.info(f"[ETL Lugares] Archivo leído con encoding: {enc}")
            return lineas
        except UnicodeDecodeError:
            logger.debug(f"[ETL Lugares] Encoding {enc} falló.")
            continue

    logger.warning(f"[ETL Lugares] Usando encoding con errors='replace'")
    with open(ruta, 'r', encoding='latin-1', errors='replace') as f:
        return f.readlines()


def _procesar_linea_lugar(linea: str, num_linea: int, resultado: ResultadoETLLugares, ejecucion=None):
    """
    Procesa una sola línea del archivo de lugares.
    Modifica resultado in-place.
    """
    from etl_app.services.parsers import parse_linea_lugar, es_header_lugares
    from etl_app.services.normalizers import (
        normalizar_nombre,
        normalizar_direccion,
        normalizar_coordenadas,
        corregir_encoding,
    )
    from etl_app.services.deduplicator import generar_hash_lugar, es_duplicado_lugar
    from etl_app.services.validators import validar_linea_lugar, validar_coordenadas
    from etl_app.models import Lugar, Direccion, Georeferencia, ErrorImportacion

    linea_limpia = linea.strip()

    # ── Omitir líneas vacías ───────────────────────────────────
    if not linea_limpia:
        resultado.omitidos += 1
        return

    if ejecucion:
        ejecucion.registros_procesados += 1

    # ── Omitir header explícitamente ───────────────────────────
    if es_header_lugares(linea_limpia):
        resultado.omitidos += 1
        logger.debug(f"[ETL Lugares] Header ignorado en línea {num_linea}")
        return

    # ── PASO 1: Parsear ────────────────────────────────────────
    parsed = parse_linea_lugar(linea_limpia)

    if not parsed:
        logger.warning(f"[ETL Lugares] Línea {num_linea} no pudo parsearse: {linea_limpia!r}")
        _registrar_error_lugar(
            linea_numero=num_linea,
            contenido=linea_limpia,
            tipo='formato_invalido',
            mensaje="La línea no tiene 3 columnas separadas por ';'",
        )
        resultado.errores += 1
        if ejecucion: ejecucion.errores += 1
        resultado.lista_errores.append({
            'linea': num_linea,
            'contenido': linea_limpia,
            'error': 'Formato inválido (necesita 3 columnas con ;)',
        })
        return

    nombre_raw = parsed['nombre_raw']
    direccion_raw = parsed['direccion_raw']
    georef_raw = parsed['georef_raw']

    # ── PASO 2: Validar ────────────────────────────────────────
    es_valido, errores_val = validar_linea_lugar(parsed)
    if not es_valido:
        msg = '; '.join(errores_val)
        _registrar_error_lugar(num_linea, linea_limpia, 'formato_invalido', msg)
        resultado.errores += 1
        if ejecucion: ejecucion.errores += 1
        resultado.lista_errores.append({'linea': num_linea, 'contenido': linea_limpia, 'error': msg})
        return

    # ── PASO 3: Normalizar ─────────────────────────────────────
    # Corregir encoding del nombre y dirección primero
    nombre_corregido = corregir_encoding(nombre_raw)
    nombre_norm = normalizar_nombre(nombre_corregido)

    dir_info = normalizar_direccion(direccion_raw)  # Incluye correccion de encoding
    coordenadas = normalizar_coordenadas(georef_raw)

    # ── PASO 4: Generar hash ───────────────────────────────────
    hash_registro = generar_hash_lugar(nombre_norm, dir_info['direccion_completa'])

    # ── PASO 5: Deduplicar ─────────────────────────────────────
    if es_duplicado_lugar(hash_registro):
        logger.info(f"[ETL Lugares] DUP: {nombre_norm}")
        resultado.duplicados += 1
        if ejecucion: ejecucion.duplicados_eliminados += 1
        resultado.lista_duplicados.append({
            'nombre': nombre_norm,
            'direccion': dir_info['direccion_completa'],
        })
        return

    # ── PASO 6: Validar coordenadas ────────────────────────────
    coords_validas = False
    if coordenadas:
        lat, lon = coordenadas
        coord_valida, msg_coord = validar_coordenadas(lat, lon)
        if coord_valida:
            coords_validas = True
        else:
            logger.warning(f"[ETL Lugares] Coordenadas inválidas en {nombre_norm}: {msg_coord}")
            _registrar_error_lugar(num_linea, linea_limpia, 'coordenada_invalida', msg_coord)
            resultado.sin_coordenadas += 1
    else:
        resultado.sin_coordenadas += 1
        logger.warning(f"[ETL Lugares] Sin coordenadas: {nombre_norm}")

    # ── PASO 7: Insertar en BD (transacción atómica) ───────────
    try:
        with transaction.atomic():
            # 1. Crear el registro principal en la tabla Lugares
            lugar = Lugar.objects.create(
                nombre_lugar=nombre_norm,
                hash_registro=hash_registro
            )

            # 2. Crear el registro en la tabla Direcciones asociado al Lugar
            # Campos requeridos por la regla: ID (autogenerado), nombre_calle, numero_calle, ciudad_estado_provincia, país
            Direccion.objects.create(
                lugar=lugar,
                nombre_calle=dir_info.get('nombre_calle', ''),
                numero_calle=dir_info.get('numero_calle', ''),
                ciudad_estado_provincia=dir_info.get('ciudad_estado_provincia', ''),
                pais=dir_info.get('pais', ''),
                direccion_completa=dir_info.get('direccion_completa', '') # Opcional para auditoría
            )

            # 3. Crear el registro en la tabla Georeferencias (si existen coordenadas válidas)
            coords_validas = coordenadas is not None
            if coords_validas:
                Georeferencia.objects.create(
                    lugar=lugar,
                    latitud=Decimal(str(coordenadas[0])),
                    longitud=Decimal(str(coordenadas[1]))
                )
            else:
                resultado.sin_coordenadas += 1

            # 4. Actualizar estadísticas de éxito
            resultado.insertados += 1
            if ejecucion: ejecucion.registros_consolidados += 1
            resultado.lista_insertados.append({
                'id': lugar.id,
                'nombre': lugar.nombre_lugar,
                'direccion': dir_info['direccion_completa'],
                'lat': str(coordenadas[0]) if coords_validas else 'N/A',
                'lon': str(coordenadas[1]) if coords_validas else 'N/A',
            })
            
            logger.info(
                f"[ETL Lugares] OK: {lugar.nombre_lugar} "
                f"{'(' + str(coordenadas[0]) + ', ' + str(coordenadas[1]) + ')' if coords_validas else '(sin coords)'}"
            )

    except Exception as e:
        logger.error(f"[ETL Lugares] Error al guardar línea {num_linea}: {e}")
        _registrar_error_lugar(num_linea, linea_limpia, 'otro', str(e))
        resultado.errores += 1
        if ejecucion: ejecucion.errores += 1
        resultado.lista_errores.append({
            'linea': num_linea, 
            'contenido': linea_limpia, 
            'error': str(e)
        })

def _registrar_error_lugar(linea_numero: int, contenido: str, tipo: str, mensaje: str):
    """Registra un error de importación de lugares en la BD."""
    from etl_app.models import ErrorImportacion
    try:
        ErrorImportacion.objects.create(
            dataset='lugares',
            linea_numero=linea_numero,
            contenido_original=contenido[:1000],
            tipo_error=tipo,
            mensaje_error=mensaje[:2000],
        )
    except Exception as e:
        logger_errores.error(f"[ETL Lugares] No se pudo guardar ErrorImportacion: {e}")
