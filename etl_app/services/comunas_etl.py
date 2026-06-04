import os
import logging
from django.utils import timezone
from etl_app.models import Comuna, EjecucionETL, ErrorImportacion
from etl_app.services.normalizers import NormalizadorService
from etl_app.services.external_apis import fetch_comuna_info

logger = logging.getLogger(__name__)

class ComunasETLService:
    def __init__(self, file_path):
        self.file_path = file_path
        self.ejecucion = None

    def procesar(self):
        """
        Punto de entrada principal para procesar el dataset de Comunas.
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.file_path}")

        # Iniciar auditoría (RF-21, RF-22)
        self.ejecucion = EjecucionETL.objects.create(
            dataset='comunas',
            fecha_inicio=timezone.now()
        )

        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
                lineas = f.readlines()
        except Exception as e:
            logger.error(f"Error leyendo archivo de comunas: {e}")
            self.finalizar_ejecucion()
            return self.ejecucion

        self.ejecucion.registros_leidos = len(lineas)
        
        # Procesar línea por línea
        for i, linea in enumerate(lineas, start=1):
            nombre_original = linea.strip()
            if not nombre_original:
                continue
                
            self.ejecucion.registros_procesados += 1
            
            # Normalización (RF-03)
            # Normalizamos convirtiendo a Title Case y limpiando espacios
            nombre_normalizado = " ".join(nombre_original.title().split())
            
            # Verificar duplicados (RF-04, RF-09)
            if Comuna.objects.filter(nombre_normalizado=nombre_normalizado).exists():
                self.ejecucion.duplicados_eliminados += 1
                # Ignorar registro repetido (RF-10)
                continue
                
            # Consulta API externa (RF-05, RF-06)
            api_info = fetch_comuna_info(nombre_normalizado)
            
            try:
                # Consolidación y almacenamiento (RF-07, RF-08)
                Comuna.objects.create(
                    nombre_original=nombre_original,
                    nombre_normalizado=nombre_normalizado,
                    region=api_info.get("region"),
                    habitantes=api_info.get("habitantes")
                )
                self.ejecucion.registros_consolidados += 1
            except Exception as e:
                self.ejecucion.errores += 1
                ErrorImportacion.objects.create(
                    dataset='comunas',
                    linea_numero=i,
                    contenido_original=nombre_original,
                    tipo_error='otro',
                    mensaje_error=str(e)
                )

        self.finalizar_ejecucion()
        return self.ejecucion

    def finalizar_ejecucion(self):
        if self.ejecucion:
            self.ejecucion.fecha_fin = timezone.now()
            self.ejecucion.save()
