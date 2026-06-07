import os
import logging
from django.utils import timezone
from etl_app.models import Comuna, EjecucionETL, ErrorImportacion
from etl_app.services.external_apis import fetch_comuna_info
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class ResultadoETL:
    total_lineas: int = 0
    insertados: int = 0
    duplicados: int = 0
    errores: int = 0
    omitidos: int = 0
    lista_insertados: list = field(default_factory=list)
    lista_duplicados: list = field(default_factory=list)
    lista_errores: list = field(default_factory=list)

    def resumen(self) -> str:
        return (
            f"[RESUMEN ETL COMUNAS]\n"
            f"  Total líneas procesadas : {self.total_lineas}\n"
            f"  Insertados              : {self.insertados}\n"
            f"  Duplicados (omitidos)   : {self.duplicados}\n"
            f"  Errores                 : {self.errores}\n"
            f"  Líneas omitidas         : {self.omitidos}\n"
        )

class ComunasETLService:
    def __init__(self, file_path):
        self.file_path = file_path
        self.ejecucion = None

    def procesar(self):
        """
        Punto de entrada principal para procesar el dataset de Comunas.
        Retorna un ResultadoETL (compatibilidad con views/utils).
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.file_path}")

        # Iniciar auditoría
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
            return self.ejecucion  # fallback: mantener comportamiento previo si lectura falla

        resultado = ResultadoETL()
        resultado.total_lineas = len(lineas)
        self.ejecucion.registros_leidos = len(lineas)

        # Procesar línea por línea
        for i, linea in enumerate(lineas, start=1):
            nombre_original = linea.strip()
            if not nombre_original:
                resultado.omitidos += 1
                continue

            self.ejecucion.registros_procesados += 1

            # Normalización
            nombre_normalizado = " ".join(nombre_original.title().split())

            # Duplicado
            if Comuna.objects.filter(nombre_normalizado=nombre_normalizado).exists():
                self.ejecucion.duplicados_eliminados += 1
                resultado.duplicados += 1
                resultado.lista_duplicados.append({
                    'linea': i,
                    'nombre': nombre_normalizado,
                })
                continue

            # Consulta API externa
            api_info = fetch_comuna_info(nombre_normalizado)

            try:
                comuna = Comuna.objects.create(
                    nombre_original=nombre_original,
                    nombre_normalizado=nombre_normalizado,
                    region=api_info.get("region") if api_info else None,
                    habitantes=api_info.get("habitantes") if api_info else None
                )
                self.ejecucion.registros_consolidados += 1
                resultado.insertados += 1
                resultado.lista_insertados.append({
                    'id': comuna.id,
                    'linea': i,
                    'nombre': nombre_normalizado,
                })
            except Exception as e:
                self.ejecucion.errores += 1
                resultado.errores += 1
                ErrorImportacion.objects.create(
                    dataset='comunas',
                    linea_numero=i,
                    contenido_original=nombre_original,
                    tipo_error='otro',
                    mensaje_error=str(e)
                )
                resultado.lista_errores.append({
                    'linea': i,
                    'contenido': nombre_original,
                    'error': str(e),
                })

        # Finalizar auditoría y devolver resultado compatible con vistas
        self.finalizar_ejecucion()
        return resultado

    def finalizar_ejecucion(self):
        if self.ejecucion:
            self.ejecucion.fecha_fin = timezone.now()
            self.ejecucion.save()

