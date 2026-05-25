"""
management/commands/import_lugares.py
Comando de management Django para importar el dataset de Lugares desde la línea de comandos.

Uso:
    python manage.py import_lugares DATOS2026-3.TXT
    python manage.py import_lugares DATOS2026-3.TXT --limpiar
    python manage.py import_lugares DATOS2026-3.TXT --dry-run
    python manage.py import_lugares DATOS2026-3.TXT --verbosity 2
"""

import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('etl_app')


class Command(BaseCommand):
    help = (
        'Importa el dataset de Lugares desde un archivo TXT.\n'
        'Formato esperado: "Nombre;Dirección;Georeferencia" (separado por ;)\n'
        'Ejemplo: python manage.py import_lugares DATOS2026-3.TXT'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ruta_archivo',
            type=str,
            help='Ruta al archivo TXT de lugares (relativa o absoluta)',
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            default=False,
            help='Eliminar todos los Lugares existentes antes de importar',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Procesar el archivo sin guardar en BD (solo mostrar estadísticas)',
        )

    def handle(self, *args, **options):
        ruta_str = options['ruta_archivo']
        limpiar = options['limpiar']
        dry_run = options['dry_run']
        verbosity = options['verbosity']

        # ── Resolver ruta ──────────────────────────────────────
        ruta = Path(ruta_str)
        if not ruta.is_absolute():
            ruta_relativa = Path.cwd() / ruta
            if ruta_relativa.exists():
                ruta = ruta_relativa
            else:
                from django.conf import settings
                ruta_base = settings.BASE_DIR / ruta
                if ruta_base.exists():
                    ruta = ruta_base

        if not ruta.exists():
            raise CommandError(
                f'Archivo no encontrado: {ruta_str}\n'
                f'Rutas buscadas:\n'
                f'  - {Path.cwd() / ruta_str}'
            )

        self.stdout.write(
            self.style.HTTP_INFO(f'\n[ETL Lugares] Archivo: {ruta.name}')
        )
        self.stdout.write(f'  Ruta completa: {ruta}')

        # ── Limpiar BD ─────────────────────────────────────────
        if limpiar and not dry_run:
            from etl_app.models import Lugar, ErrorImportacion
            count = Lugar.objects.count()
            Lugar.objects.all().delete()
            ErrorImportacion.objects.filter(dataset='lugares').delete()
            self.stdout.write(
                self.style.WARNING(f'  BD limpiada: {count} lugares eliminados (+ direcciones y georef).')
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN: No se guardará nada en BD.'))

        # ── Ejecutar ETL ───────────────────────────────────────
        self.stdout.write('\n[Procesando líneas...]\n')

        try:
            if dry_run:
                resultado = self._dry_run_lugares(ruta, verbosity)
            else:
                from etl_app.services.lugares_etl import procesar_archivo_lugares
                resultado = procesar_archivo_lugares(ruta)

        except FileNotFoundError as e:
            raise CommandError(str(e))
        except Exception as e:
            logger.error(f'[Command import_lugares] Error inesperado: {e}', exc_info=True)
            raise CommandError(f'Error durante el ETL: {e}')

        # ── Mostrar resumen ────────────────────────────────────
        self._mostrar_resumen(resultado, verbosity)

    def _dry_run_lugares(self, ruta: Path, verbosity: int):
        """
        Ejecuta el parseo SIN guardar en BD.
        """
        from etl_app.services.parsers import parse_linea_lugar, es_header_lugares
        from etl_app.services.normalizers import (
            normalizar_nombre, normalizar_direccion,
            normalizar_coordenadas, corregir_encoding
        )
        from etl_app.services.lugares_etl import ResultadoETLLugares

        resultado = ResultadoETLLugares()

        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        lineas = []
        for enc in encodings:
            try:
                with open(ruta, 'r', encoding=enc) as f:
                    lineas = f.readlines()
                break
            except UnicodeDecodeError:
                continue

        resultado.total_lineas = len(lineas)

        for num, linea in enumerate(lineas, 1):
            linea = linea.strip()
            if not linea:
                resultado.omitidos += 1
                continue
            if es_header_lugares(linea):
                resultado.omitidos += 1
                continue

            parsed = parse_linea_lugar(linea)
            if not parsed:
                resultado.errores += 1
                resultado.lista_errores.append({
                    'linea': num, 'contenido': linea, 'error': 'Formato inválido'
                })
                if verbosity >= 2:
                    self.stdout.write(self.style.ERROR(f'  [ERR] L{num}: {linea[:60]}'))
                continue

            nombre_norm = normalizar_nombre(corregir_encoding(parsed['nombre_raw']))
            coords = normalizar_coordenadas(parsed['georef_raw'])

            if verbosity >= 2:
                coords_str = f"({coords[0]}, {coords[1]})" if coords else "sin coords"
                self.stdout.write(f'  [OK] {nombre_norm} — {coords_str}')

            resultado.insertados += 1
            if not coords:
                resultado.sin_coordenadas += 1

        return resultado

    def _mostrar_resumen(self, resultado, verbosity: int):
        """Muestra el resumen del ETL de Lugares."""

        if verbosity >= 2 and resultado.lista_insertados:
            self.stdout.write(f'\n[Registros insertados ({resultado.insertados})]')
            for r in resultado.lista_insertados:
                coords = f"({r.get('lat', '?')}, {r.get('lon', '?')})"
                if r.get('lat') == 'N/A':
                    coords = '[sin coordenadas]'
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK]  {r['nombre']} {coords}")
                )

        if verbosity >= 1 and resultado.lista_duplicados:
            self.stdout.write(f'\n[Duplicados omitidos ({resultado.duplicados})]')
            for d in resultado.lista_duplicados[:10]:
                self.stdout.write(
                    self.style.WARNING(f"  [DUP] {d['nombre']}")
                )
            if resultado.duplicados > 10:
                self.stdout.write(f'  ... y {resultado.duplicados - 10} más.')

        if resultado.lista_errores:
            self.stdout.write(f'\n[Errores ({resultado.errores})]')
            for e in resultado.lista_errores:
                self.stdout.write(
                    self.style.ERROR(
                        f"  [ERR] L{e['linea']}: {e['contenido'][:50]} → {e['error']}"
                    )
                )

        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.HTTP_INFO('[RESUMEN FINAL — ETL LUGARES]'))
        self.stdout.write(f'  Total líneas       : {resultado.total_lineas}')
        self.stdout.write(self.style.SUCCESS(f'  Insertados         : {resultado.insertados}'))
        self.stdout.write(self.style.WARNING(f'  Duplicados         : {resultado.duplicados}'))
        self.stdout.write(f'  Sin coordenadas    : {resultado.sin_coordenadas}')
        self.stdout.write(self.style.ERROR(f'  Errores            : {resultado.errores}'))
        self.stdout.write(f'  Líneas omitidas    : {resultado.omitidos}')
        self.stdout.write('─' * 50)

        if resultado.errores == 0:
            self.stdout.write(self.style.SUCCESS('\n✓ ETL completado sin errores.\n'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠ ETL completado con {resultado.errores} errores. '
                    f'Revise logs/etl.log y /admin/etl_app/errorimportacion/\n'
                )
            )
