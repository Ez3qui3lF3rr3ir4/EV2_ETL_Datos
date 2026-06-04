import logging
from django.core.management.base import BaseCommand
from etl_app.models import (
    Famoso, 
    Lugar, 
    Direccion, 
    Georeferencia, 
    Comuna, 
    EjecucionETL, 
    ErrorImportacion
)

logger = logging.getLogger('etl_app')

class Command(BaseCommand):
    help = 'Elimina todos los datos procesados por el sistema ETL en la base de datos local (Famosos, Lugares, Comunas, Auditorías y Errores).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-input',
            action='store_true',
            default=False,
            help='No solicitar confirmación del usuario antes de borrar los datos.',
        )

    def handle(self, *args, **options):
        no_input = options['no_input']

        if not no_input:
            self.stdout.write(self.style.WARNING(
                "¡ADVERTENCIA! Esta acción eliminará permanentemente TODOS los datos de la aplicación ETL "
                "(Famosos, Lugares, Direcciones, Georeferencias, Comunas, Registros de Auditoría y Errores).\n"
            ))
            confirmacion = input("¿Estás seguro de que deseas continuar? Escribe 'yes' para confirmar: ")
            
            if confirmacion.lower() != 'yes':
                self.stdout.write(self.style.ERROR("Operación cancelada por el usuario."))
                return

        self.stdout.write("Borrando datos de Famosos...")
        famosos_count, _ = Famoso.objects.all().delete()
        
        self.stdout.write("Borrando datos de Lugares (y sus relaciones)...")
        lugares_count, _ = Lugar.objects.all().delete()
        # Las direcciones y georeferencias se borran en cascada por el Lugar, pero si hubiera huerfanos:
        Direccion.objects.all().delete()
        Georeferencia.objects.all().delete()
        
        self.stdout.write("Borrando datos de Comunas...")
        comunas_count, _ = Comuna.objects.all().delete()
        
        self.stdout.write("Borrando registros de Ejecuciones ETL (Auditoría)...")
        ejecuciones_count, _ = EjecucionETL.objects.all().delete()
        
        self.stdout.write("Borrando registros de Errores de Importación...")
        errores_count, _ = ErrorImportacion.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("\n¡Base de datos limpiada con éxito!"))
        self.stdout.write(f"- Famosos eliminados: {famosos_count}")
        self.stdout.write(f"- Lugares eliminados: {lugares_count}")
        self.stdout.write(f"- Comunas eliminadas: {comunas_count}")
        self.stdout.write(f"- Ejecuciones de auditoría eliminadas: {ejecuciones_count}")
        self.stdout.write(f"- Errores eliminados: {errores_count}")
