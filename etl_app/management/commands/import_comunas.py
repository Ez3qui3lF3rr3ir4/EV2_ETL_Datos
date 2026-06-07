import logging
from pathlib import Path
# pyrefly: ignore [missing-import]
from django.core.management.base import BaseCommand, CommandError
from etl_app.services.comunas_etl import ComunasETLService

logger = logging.getLogger('etl_app')

class Command(BaseCommand):
    help = (
        'Importa el dataset de Comunas desde un archivo de texto.\n'
        'Formato esperado: Una comuna por línea.\n'
        'Ejemplo: python manage.py import_comunas comunas.txt'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ruta_archivo',
            type=str,
            help='Ruta al archivo TXT de comunas (relativa o absoluta)',
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            default=False,
            help='Eliminar todas las Comunas existentes antes de importar',
        )

    def handle(self, *args, **options):
        ruta_str = options['ruta_archivo']
        limpiar = options['limpiar']

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
            raise CommandError(f'Archivo no encontrado: {ruta_str}')

        self.stdout.write(self.style.HTTP_INFO(f'\n[ETL Comunas] Archivo: {ruta.name}'))

        if limpiar:
            from etl_app.models import Comuna, EjecucionETL
            Comuna.objects.all().delete()
            self.stdout.write(self.style.WARNING('  BD limpiada: Registros de Comunas eliminados.'))

        self.stdout.write('\n[Procesando comunas...]\n')

        try:
            service = ComunasETLService(ruta)
            service.procesar()
            ejecucion = service.ejecucion
            
            self.stdout.write('\n' + '─' * 50)
            self.stdout.write(self.style.HTTP_INFO('[RESUMEN FINAL — ETL COMUNAS]'))
            self.stdout.write(f'  Registros leídos      : {ejecucion.registros_leidos}')
            self.stdout.write(self.style.SUCCESS(f'  Registros procesados  : {ejecucion.registros_procesados}'))
            self.stdout.write(self.style.WARNING(f'  Duplicados eliminados : {ejecucion.duplicados_eliminados}'))
            self.stdout.write(self.style.SUCCESS(f'  Registros consolidados: {ejecucion.registros_consolidados}'))
            self.stdout.write(self.style.ERROR(f'  Errores               : {ejecucion.errores}'))
            self.stdout.write('─' * 50)
            
            if ejecucion.errores == 0:
                self.stdout.write(self.style.SUCCESS('\n✓ ETL completado sin errores.\n'))
            else:
                self.stdout.write(self.style.WARNING(f'\n⚠ ETL completado con {ejecucion.errores} errores.\n'))

        except Exception as e:
            logger.error(f'[Command import_comunas] Error inesperado: {e}', exc_info=True)
            raise CommandError(f'Error durante el ETL: {e}')
