import time
from django.core.management.base import BaseCommand
from django.db import transaction
from etl_app.models import Famoso
from etl_app.services.external_apis import fetch_famoso_image

class Command(BaseCommand):
    help = 'Actualiza las imágenes de los famosos que no tienen una imagen asignada.'

    def handle(self, *args, **options):
        famosos_sin_imagen = Famoso.objects.filter(imagen_url__isnull=True)
        total = famosos_sin_imagen.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Todos los famosos tienen imagen."))
            return

        self.stdout.write(self.style.WARNING(f"Se encontraron {total} famosos sin imagen. Intentando actualizar..."))

        actualizados = 0
        errores = 0

        for famoso in famosos_sin_imagen:
            self.stdout.write(f"Buscando imagen para: {famoso.nombre_completo}...")
            try:
                img_data = fetch_famoso_image(famoso.nombre_completo)
                if img_data and img_data.get("url"):
                    famoso.imagen_url = img_data["url"]
                    famoso.imagen_fuente = img_data.get("fuente", "Wikipedia")
                    famoso.imagen_fecha = img_data.get("fecha")
                    famoso.save(update_fields=['imagen_url', 'imagen_fuente', 'imagen_fecha'])
                    self.stdout.write(self.style.SUCCESS(f"  [OK] Imagen encontrada y actualizada."))
                    actualizados += 1
                else:
                    self.stdout.write(self.style.WARNING(f"  [WARN] No se encontró imagen."))
                    errores += 1
                
                # Pausa para no saturar la API
                time.sleep(0.5)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  [ERROR] Ocurrió un error: {e}"))
                errores += 1

        self.stdout.write(self.style.SUCCESS(f"Proceso finalizado. Actualizados: {actualizados}. No encontrados: {errores}."))
