"""
management/commands/import_famosos.py
Comando de management Django para importar el dataset de Famosos desde la línea de comandos.

Uso:
    python manage.py import_famosos DATOS2026-2.txt
    python manage.py import_famosos DATOS2026-2.txt --limpiar
    python manage.py import_famosos DATOS2026-2.txt --verbosity 2

Opciones:
    ruta_archivo    Ruta al archivo TXT (relativa al directorio del proyecto o absoluta)
    --limpiar       Elimina todos los Famosos existentes antes de importar
    --dry-run       Procesa el archivo pero NO guarda en BD (solo muestra estadísticas)
"""

import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('etl_app')


class Command(BaseCommand):
    help = (
        'Importa el dataset de Famosos desde un archivo TXT.\n'
        'Formato esperado: "N. Nombre - Fecha" (una por línea)\n'
        'Ejemplo: python manage.py import_famosos DATOS2026-2.txt'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ruta_archivo',
            type=str,
            help='Ruta al archivo TXT de famosos (relativa o absoluta)',
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            default=False,
            help='Eliminar todos los Famosos existentes antes de importar',
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

        # ── Resolver ruta del archivo ──────────────────────────
        ruta = Path(ruta_str)
        if not ruta.is_absolute():
            # Buscar relativo al directorio actual primero
            ruta_relativa = Path.cwd() / ruta
            if ruta_relativa.exists():
                ruta = ruta_relativa
            else:
                # Buscar relativo a BASE_DIR (donde está manage.py)
                from django.conf import settings
                ruta_base = settings.BASE_DIR / ruta
                if ruta_base.exists():
                    ruta = ruta_base

        if not ruta.exists():
            raise CommandError(
                f'Archivo no encontrado: {ruta_str}\n'
                f'Rutas buscadas:\n'
                f'  - {Path.cwd() / ruta_str}\n'
                f'  - (ruta absoluta)'
            )

        self.stdout.write(
            self.style.HTTP_INFO(f'\n[ETL Famosos] Archivo: {ruta.name}')
        )
        self.stdout.write(f'  Ruta completa: {ruta}')

        # ── Limpiar BD si se solicitó ──────────────────────────
        if limpiar and not dry_run:
            from etl_app.models import Famoso, ErrorImportacion
            count = Famoso.objects.count()
            Famoso.objects.all().delete()
            ErrorImportacion.objects.filter(dataset='famosos').delete()
            self.stdout.write(
                self.style.WARNING(f'  BD limpiada: {count} registros de Famosos eliminados.')
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN: No se guardará nada en BD.'))

        # ── Ejecutar ETL ───────────────────────────────────────
        self.stdout.write('\n[Procesando líneas...]\n')

        try:
            if dry_run:
                resultado = self._dry_run_famosos(ruta, verbosity)
            else:
                from etl_app.services.famosos_etl import procesar_archivo_famosos
                resultado = procesar_archivo_famosos(ruta)

        except FileNotFoundError as e:
            raise CommandError(str(e))
        except Exception as e:
            logger.error(f'[Command import_famosos] Error inesperado: {e}', exc_info=True)
            raise CommandError(f'Error durante el ETL: {e}')

        # ── Mostrar resumen ────────────────────────────────────
        self._mostrar_resumen(resultado, verbosity)

    def _dry_run_famosos(self, ruta: Path, verbosity: int):
        """
        Ejecuta el parseo y normalización SIN guardar en BD.
        Útil para validar el archivo antes de importar.
        """
        from etl_app.services.parsers import parse_linea_famoso
        from etl_app.services.normalizers import normalizar_nombre, normalizar_fecha
        from etl_app.services.famosos_etl import ResultadoETL

        resultado = ResultadoETL()

        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
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

            parsed = parse_linea_famoso(linea)
            if not parsed:
                resultado.errores += 1
                resultado.lista_errores.append({
                    'linea': num,
                    'contenido': linea,
                    'error': 'Formato no reconocido',
                })
                if verbosity >= 2:
                    self.stdout.write(self.style.ERROR(f'  [ERR] L{num}: {linea}'))
                continue

            nombre_norm = normalizar_nombre(parsed['nombre_raw'])
            fecha_obj, es_aprox, fecha_fmt = normalizar_fecha(parsed['fecha_raw'])

            if es_aprox:
                resultado.aproximados += 1
                if verbosity >= 2:
                    self.stdout.write(
                        self.style.WARNING(f'  [APROX] {nombre_norm} — {parsed["fecha_raw"]}')
                    )
            else:
                resultado.insertados += 1  # En dry-run "insertados" = parseados OK
                if verbosity >= 2:
                    self.stdout.write(f'  [OK] {nombre_norm} — {fecha_fmt}')

        return resultado

    def _mostrar_resumen(self, resultado, verbosity: int):
        """Muestra el resumen del ETL en la consola con colores."""

        # Detalle de insertados (verbosity >= 2)
        if verbosity >= 2 and resultado.lista_insertados:
            self.stdout.write(f'\n[Registros insertados ({resultado.insertados})]')
            for r in resultado.lista_insertados:
                cumple = ' 🎂 ¡CUMPLEAÑOS HOY!' if r.get('cumpleanos') else ''
                aprox = ' [FECHA APROX.]' if r.get('es_aproximada') else ''
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [OK]  {r['nombre']} — {r.get('fecha_formateada') or r['fecha']}"
                        f"{aprox}{cumple}"
                    )
                )

        # Detalle de duplicados (verbosity >= 1)
        if verbosity >= 1 and resultado.lista_duplicados:
            self.stdout.write(f'\n[Duplicados omitidos ({resultado.duplicados})]')
            for d in resultado.lista_duplicados[:10]:
                self.stdout.write(
                    self.style.WARNING(f"  [DUP] {d['nombre']} — {d['fecha']}")
                )
            if resultado.duplicados > 10:
                self.stdout.write(f'  ... y {resultado.duplicados - 10} más.')

        # Detalle de fechas aproximadas
        if resultado.lista_aproximados:
            self.stdout.write(f'\n[Fechas aproximadas o históricas ({resultado.aproximados})]')
            for a in resultado.lista_aproximados:
                self.stdout.write(
                    self.style.WARNING(f"  [APROX] {a['nombre']} — {a['fecha']}")
                )

        # Detalle de errores
        if resultado.lista_errores:
            self.stdout.write(f'\n[Errores ({resultado.errores})]')
            for e in resultado.lista_errores:
                self.stdout.write(
                    self.style.ERROR(
                        f"  [ERR] L{e['linea']}: {e['contenido'][:60]} → {e['error']}"
                    )
                )

        # Resumen final
        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.HTTP_INFO('[RESUMEN FINAL — ETL FAMOSOS]'))
        self.stdout.write(f'  Total líneas      : {resultado.total_lineas}')
        self.stdout.write(
            self.style.SUCCESS(f'  Insertados        : {resultado.insertados}')
        )
        self.stdout.write(
            self.style.WARNING(f'  Duplicados        : {resultado.duplicados}')
        )
        self.stdout.write(
            self.style.WARNING(f'  Fecha aproximada  : {resultado.aproximados}')
        )
        self.stdout.write(
            self.style.ERROR(f'  Errores           : {resultado.errores}')
        )
        self.stdout.write(f'  Líneas omitidas   : {resultado.omitidos}')
        self.stdout.write('─' * 50)

        # Mensaje final de estado
        if resultado.errores == 0:
            self.stdout.write(self.style.SUCCESS('\n✓ ETL completado sin errores.\n'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠ ETL completado con {resultado.errores} errores. '
                    f'Revise logs/etl.log y /admin/etl_app/errorimportacion/\n'
                )
            )
