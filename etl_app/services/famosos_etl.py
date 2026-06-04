"""
services/famosos_etl.py — ETL completo para el dataset de Famosos (DATOS2026-2.txt).

Flujo ETL:
  1. Leer el archivo TXT línea por línea
  2. Parsear cada línea (extraer número, nombre, fecha)
  3. Normalizar nombre y fecha
  4. Validar los datos
  5. Generar hash único (deduplicación)
  6. Verificar si ya existe en BD (duplicado semántico)
  7. Crear registro en Famoso (con edad y cumpleaños calculados)
  8. Registrar errores en ErrorImportacion

Función principal:
  - procesar_archivo_famosos(ruta_archivo)  → ResultadoETL
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field

from django.db import transaction

logger = logging.getLogger('etl_app')
logger_errores = logging.getLogger('etl_app.errores')


# ══════════════════════════════════════════════════════════════
# ESTRUCTURA DE RESULTADO
# ══════════════════════════════════════════════════════════════

@dataclass
class ResultadoETL:
    """
    Resultado completo de una ejecución del proceso ETL.
    Usado para mostrar el resumen en consola y en la vista web.
    """
    total_lineas: int = 0
    insertados: int = 0
    duplicados: int = 0
    errores: int = 0
    omitidos: int = 0        # Líneas vacías, headers, etc.
    aproximados: int = 0     # Registros con fecha aproximada (insertados igual)
    lista_insertados: list = field(default_factory=list)
    lista_duplicados: list = field(default_factory=list)
    lista_errores: list = field(default_factory=list)
    lista_aproximados: list = field(default_factory=list)

    def resumen(self) -> str:
        """Genera un string de resumen legible para consola."""
        return (
            f"[RESUMEN ETL FAMOSOS]\n"
            f"  Total líneas procesadas : {self.total_lineas}\n"
            f"  Insertados              : {self.insertados}\n"
            f"  Duplicados (omitidos)   : {self.duplicados}\n"
            f"  Con fecha aproximada    : {self.aproximados}\n"
            f"  Errores de parseo       : {self.errores}\n"
            f"  Líneas omitidas         : {self.omitidos}\n"
        )


# ══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL ETL
# ══════════════════════════════════════════════════════════════

def procesar_archivo_famosos(ruta_archivo: str | Path) -> ResultadoETL:
    """
    Ejecuta el proceso ETL completo sobre el archivo de famosos.

    El archivo puede ser leído desde:
    - Una ruta en disco (str o Path)
    - Se intenta UTF-8 primero, luego latin-1 como fallback

    Parámetros:
        ruta_archivo: Ruta al archivo TXT (DATOS2026-2.txt)

    Retorna:
        ResultadoETL con estadísticas completas del proceso.
    """
    from etl_app.services.parsers import parse_linea_famoso
    from etl_app.services.normalizers import normalizar_nombre, normalizar_fecha
    from etl_app.services.deduplicator import (
        generar_hash_famoso,
        es_duplicado_famoso,
        buscar_famoso_por_nombre,
    )
    from etl_app.services.validators import validar_linea_famoso, validar_fecha_nacimiento
    from etl_app.models import Famoso, ErrorImportacion, EjecucionETL
    from django.utils import timezone

    ruta = Path(ruta_archivo)
    resultado = ResultadoETL()

    ejecucion = EjecucionETL.objects.create(
        dataset='famosos',
        fecha_inicio=timezone.now()
    )

    if not ruta.exists():
        logger.error(f"[ETL Famosos] Archivo no encontrado: {ruta}")
        raise FileNotFoundError(f"Archivo no encontrado: {ruta}")

    logger.info(f"[ETL Famosos] Iniciando procesamiento: {ruta.name}")

    # ── Leer archivo con manejo de encoding ───────────────────
    lineas = _leer_archivo(ruta)
    resultado.total_lineas = len(lineas)
    ejecucion.registros_leidos = len(lineas)
    logger.info(f"[ETL Famosos] Total de líneas a procesar: {len(lineas)}")

    # ── Procesar cada línea ───────────────────────────────────
    for num_linea, linea in enumerate(lineas, start=1):
        _procesar_linea_famoso(
            linea=linea,
            num_linea=num_linea,
            resultado=resultado,
            ejecucion=ejecucion
        )

    ejecucion.fecha_fin = timezone.now()
    ejecucion.save()
    logger.info(f"[ETL Famosos] Completado. {resultado.resumen()}")
    return resultado


def _leer_archivo(ruta: Path) -> list:
    """
    Lee el archivo TXT probando encodings en orden: utf-8, latin-1, cp1252.
    Retorna lista de líneas (strings).
    """
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']

    for enc in encodings:
        try:
            with open(ruta, 'r', encoding=enc) as f:
                lineas = f.readlines()
            logger.info(f"[ETL Famosos] Archivo leído con encoding: {enc}")
            return lineas
        except UnicodeDecodeError:
            logger.debug(f"[ETL Famosos] Encoding {enc} falló, probando siguiente...")
            continue

    # Último recurso: leer ignorando errores
    logger.warning(f"[ETL Famosos] Usando encoding con errors='replace'")
    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
        return f.readlines()


def _procesar_linea_famoso(linea: str, num_linea: int, resultado: ResultadoETL, ejecucion=None):
    """
    Procesa una sola línea del archivo de famosos.
    Modifica resultado in-place.
    """
    from etl_app.services.parsers import parse_linea_famoso
    from etl_app.services.normalizers import normalizar_nombre, normalizar_fecha
    from etl_app.services.deduplicator import (
        generar_hash_famoso,
        es_duplicado_famoso,
        buscar_famoso_por_nombre,
    )
    from etl_app.services.validators import validar_linea_famoso, validar_fecha_nacimiento
    from etl_app.services.external_apis import fetch_famoso_image
    from etl_app.models import Famoso, ErrorImportacion

    linea_limpia = linea.strip()

    # ── Omitir líneas vacías ───────────────────────────────────
    if not linea_limpia:
        resultado.omitidos += 1
        return

    if ejecucion:
        ejecucion.registros_procesados += 1

    # ── PASO 1: Parsear ────────────────────────────────────────
    parsed = parse_linea_famoso(linea_limpia)

    if not parsed:
        logger.warning(f"[ETL Famosos] Línea {num_linea} no pudo parsearse: {linea_limpia!r}")
        _registrar_error(
            dataset='famosos',
            linea_numero=num_linea,
            contenido=linea_limpia,
            tipo='formato_invalido',
            mensaje=f"La línea no sigue el patrón 'N. Nombre - Fecha'",
        )
        resultado.errores += 1
        if ejecucion: ejecucion.errores += 1
        resultado.lista_errores.append({
            'linea': num_linea,
            'contenido': linea_limpia,
            'error': 'Formato de línea no reconocido',
        })
        return

    nombre_raw = parsed['nombre_raw']
    fecha_raw = parsed['fecha_raw']

    # ── PASO 2: Validar datos crudos ───────────────────────────
    es_valido, errores_validacion = validar_linea_famoso(parsed)
    if not es_valido:
        msg = '; '.join(errores_validacion)
        logger.warning(f"[ETL Famosos] Línea {num_linea} inválida: {msg}")
        _registrar_error(
            dataset='famosos',
            linea_numero=num_linea,
            contenido=linea_limpia,
            tipo='formato_invalido',
            mensaje=msg,
        )
        resultado.errores += 1
        if ejecucion: ejecucion.errores += 1
        resultado.lista_errores.append({'linea': num_linea, 'contenido': linea_limpia, 'error': msg})
        return

    # ── PASO 3: Normalizar ─────────────────────────────────────
    nombre_norm = normalizar_nombre(nombre_raw)
    fecha_obj, es_aproximada, fecha_formateada, msg_ambiguedad = normalizar_fecha(fecha_raw)

    if msg_ambiguedad:
        _registrar_error(
            dataset='famosos',
            linea_numero=num_linea,
            contenido=linea_limpia,
            tipo='fecha_ambigua',
            mensaje=msg_ambiguedad,
        )

    # ── PASO 4: Generar hash único ─────────────────────────────
    # Hash basado en nombre normalizado + fecha_original (texto crudo)
    hash_registro = generar_hash_famoso(nombre_norm, fecha_raw)

    # ── PASO 5: Deduplicación por hash exacto ─────────────────
    if es_duplicado_famoso(hash_registro):
        logger.info(f"[ETL Famosos] DUP (hash): {nombre_norm} — {fecha_raw}")
        resultado.duplicados += 1
        if ejecucion: ejecucion.duplicados_eliminados += 1
        resultado.lista_duplicados.append({
            'nombre': nombre_norm,
            'fecha': fecha_raw,
            'razon': 'hash_duplicado',
        })
        return

    # ── PASO 6: Deduplicación semántica (mismo nombre) ────────────────────────
    famoso_existente = buscar_famoso_por_nombre(nombre_norm)
    if famoso_existente:
        logger.info(f"[ETL Famosos] DUP (semántico): {nombre_norm} — {fecha_raw}")
        
        # Si el existente tiene una fecha mala/aproximada y el nuevo tiene una fecha buena,
        # aprovechamos para mejorar el dato existente en la base de datos.
        if famoso_existente.es_fecha_aproximada and not es_aproximada:
            famoso_existente.fecha_nacimiento = fecha_obj
            famoso_existente.fecha_original = fecha_raw
            famoso_existente.es_fecha_aproximada = False
            famoso_existente.save()
            logger.info(f"[ETL Famosos] UPDATED DATE: {nombre_norm} ahora tiene la fecha válida {fecha_formateada}")

        resultado.duplicados += 1
        if ejecucion: ejecucion.duplicados_eliminados += 1
        resultado.lista_duplicados.append({
            'nombre': nombre_norm,
            'fecha': fecha_raw,
            'razon': 'duplicado_semantico',
        })
        return

    # ── PASO 7: Registrar fecha aproximada (sin bloquear) ──────
    if es_aproximada:
        tipo_error = 'fecha_aproximada' if 'alrededor' in fecha_raw.lower() else 'fecha_invalida'
        _registrar_error(
            dataset='famosos',
            linea_numero=num_linea,
            contenido=linea_limpia,
            tipo=tipo_error,
            mensaje=f"Fecha no parseable, guardada como aproximada: {fecha_raw!r}",
        )
        resultado.aproximados += 1
        resultado.lista_aproximados.append({'nombre': nombre_norm, 'fecha': fecha_raw})
        logger.info(f"[ETL Famosos] APROX: {nombre_norm} — {fecha_raw}")

    # ── Fetch Image API (RF-13, RF-14) ────────────────────────
    img_data = fetch_famoso_image(nombre_norm)

    # ── PASO 8: Insertar en BD ─────────────────────────────────
    try:
        with transaction.atomic():
            famoso = Famoso.objects.create(
                nombre_completo=nombre_norm,
                fecha_nacimiento=fecha_obj,
                fecha_original=fecha_raw,
                es_fecha_aproximada=es_aproximada,
                hash_registro=hash_registro,
                imagen_url=img_data["url"] if img_data else None,
                imagen_fuente=img_data["fuente"] if img_data else None,
                imagen_fecha=img_data["fecha"] if img_data else None,
                # edad_actual y esta_de_cumpleanos se calculan en save()
            )
            resultado.insertados += 1
            if ejecucion: ejecucion.registros_consolidados += 1
            resultado.lista_insertados.append({
                'id': famoso.id,
                'nombre': famoso.nombre_completo,
                'fecha': famoso.fecha_original,
                'fecha_formateada': fecha_formateada,
                'es_aproximada': es_aproximada,
                'edad': famoso.edad_actual,
                'cumpleanos': famoso.esta_de_cumpleanos,
            })
            logger.info(
                f"[ETL Famosos] OK: {famoso.nombre_completo} "
                f"({fecha_formateada or fecha_raw})"
                f"{' [CUMPLEAÑOS HOY!]' if famoso.esta_de_cumpleanos else ''}"
            )
    except Exception as e:
        logger.error(f"[ETL Famosos] Error al guardar línea {num_linea}: {e}")
        _registrar_error(
            dataset='famosos',
            linea_numero=num_linea,
            contenido=linea_limpia,
            tipo='otro',
            mensaje=str(e),
        )
        resultado.errores += 1
        if ejecucion: ejecucion.errores += 1
        resultado.lista_errores.append({'linea': num_linea, 'contenido': linea_limpia, 'error': str(e)})


def _registrar_error(dataset: str, linea_numero: int, contenido: str,
                     tipo: str, mensaje: str):
    """
    Guarda un ErrorImportacion en la BD.
    Nunca lanza excepciones (registrar error no debe romper el ETL).
    """
    from etl_app.models import ErrorImportacion
    try:
        ErrorImportacion.objects.create(
            dataset=dataset,
            linea_numero=linea_numero,
            contenido_original=contenido[:1000],
            tipo_error=tipo,
            mensaje_error=mensaje[:2000],
        )
    except Exception as e:
        logger_errores.error(f"[ETL] No se pudo guardar ErrorImportacion: {e}")
