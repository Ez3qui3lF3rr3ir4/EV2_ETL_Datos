"""
views.py — Vistas Django para el sistema ETL.

Vistas disponibles:
  - IndexView           → Página principal con resumen de datos en BD
  - UploadFamososView   → Subir TXT y ejecutar ETL de Famosos
  - UploadLugaresView   → Subir TXT y ejecutar ETL de Lugares
  - ListaFamososView    → Listado paginado de Famosos importados
  - ListaLugaresView    → Listado paginado de Lugares importados
  - ListaErroresView    → Errores de importación registrados

Usa:
  - Django messages para feedback al usuario
  - Redirecciones POST/GET pattern
  - Django ORM para consultas
"""

import logging
import json
from pathlib import Path

from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from django.views import View
from django.views.generic import TemplateView, ListView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import difflib

from etl_app.forms import SubirFamososForm, SubirLugaresForm, SubirComunasForm
from etl_app.models import Famoso, Lugar, Direccion, ErrorImportacion, Comuna
from etl_app.utils import guardar_archivo_temporal, formatear_resultado_para_template
from etl_app.services.external_apis import get_comunas_api

logger = logging.getLogger('etl_app')


# ══════════════════════════════════════════════════════════════
# PÁGINA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class IndexView(TemplateView):
    """
    Página principal que muestra un resumen de los datos en la BD.
    """
    template_name = 'etl_app/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_famosos'] = Famoso.objects.count()
        context['total_lugares'] = Lugar.objects.count()
        context['total_direcciones'] = Direccion.objects.count()
        context['total_comunas'] = Comuna.objects.count()
        context['total_errores'] = ErrorImportacion.objects.count()
        context['famosos_cumpleanos'] = Famoso.objects.filter(
            esta_de_cumpleanos=True
        ).order_by('nombre_completo')
        context['famosos_recientes'] = Famoso.objects.order_by('-created_at')[:5]
        context['lugares_recientes'] = Lugar.objects.order_by('-created_at')[:5]
        return context


# ══════════════════════════════════════════════════════════════
# SUBIDA Y PROCESAMIENTO — FAMOSOS
# ══════════════════════════════════════════════════════════════

class UploadFamososView(View):
    """
    Vista para subir el archivo TXT de Famosos y ejecutar el ETL.

    GET:  Muestra el formulario de subida.
    POST: Recibe el archivo, lo guarda, ejecuta el ETL y redirige
          al resultado con un mensaje Django.
    """
    template_name = 'etl_app/upload_famosos.html'
    form_class = SubirFamososForm

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)

        if not form.is_valid():
            # Errores del formulario (validación de archivo)
            for field, errores in form.errors.items():
                for error in errores:
                    messages.error(request, f"Error en {field}: {error}")
            return render(request, self.template_name, {'form': form})

        archivo = form.cleaned_data['archivo']
        limpiar_antes = form.cleaned_data.get('limpiar_antes', False)

        # Limpiar BD si se solicitó
        if limpiar_antes:
            count_eliminados = Famoso.objects.count()
            Famoso.objects.all().delete()
            ErrorImportacion.objects.filter(dataset='famosos').delete()
            logger.info(f"[Vista] BD de Famosos limpiada: {count_eliminados} registros eliminados.")
            messages.warning(
                request,
                f'Base de datos limpiada: {count_eliminados} registros de Famosos eliminados.'
            )

        # Guardar archivo temporalmente
        try:
            upload_dir = Path(settings.MEDIA_ROOT) / 'uploads' / 'famosos'
            ruta_archivo = guardar_archivo_temporal(archivo, upload_dir)
        except Exception as e:
            logger.error(f"[Vista] Error al guardar archivo: {e}")
            messages.error(request, f'Error al guardar el archivo: {e}')
            return render(request, self.template_name, {'form': form})

        # Ejecutar ETL
        try:
            from etl_app.services.famosos_etl import procesar_archivo_famosos
            resultado = procesar_archivo_famosos(ruta_archivo)

            # Guardar resultado en sesión para mostrarlo en la vista de resultado
            request.session['resultado_etl'] = formatear_resultado_para_template(resultado)
            request.session['tipo_etl'] = 'famosos'

            # Mensajes de resumen
            messages.success(
                request,
                f'ETL completado: {resultado.insertados} famosos insertados, '
                f'{resultado.duplicados} duplicados omitidos, '
                f'{resultado.errores} errores.'
            )

            if resultado.aproximados > 0:
                messages.info(
                    request,
                    f'{resultado.aproximados} registros con fecha aproximada o histórica '
                    f'(marcados como es_fecha_aproximada=True).'
                )

            # Detectar cumpleaños del día
            cumpleanos_hoy = Famoso.objects.filter(esta_de_cumpleanos=True)
            if cumpleanos_hoy.exists():
                nombres = ', '.join([f.nombre_completo for f in cumpleanos_hoy[:3]])
                messages.info(request, f'🎂 ¡Cumpleaños hoy!: {nombres}')

        except FileNotFoundError as e:
            messages.error(request, f'Archivo no encontrado: {e}')
            return render(request, self.template_name, {'form': form})
        except Exception as e:
            logger.error(f"[Vista] Error en ETL Famosos: {e}", exc_info=True)
            messages.error(request, f'Error durante el procesamiento ETL: {e}')
            return render(request, self.template_name, {'form': form})

        return redirect('etl_app:resultado')


# ══════════════════════════════════════════════════════════════
# SUBIDA Y PROCESAMIENTO — LUGARES
# ══════════════════════════════════════════════════════════════

class UploadLugaresView(View):
    """
    Vista para subir el archivo TXT de Lugares y ejecutar el ETL.
    """
    template_name = 'etl_app/upload_lugares.html'
    form_class = SubirLugaresForm

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)

        if not form.is_valid():
            for field, errores in form.errors.items():
                for error in errores:
                    messages.error(request, f"Error en {field}: {error}")
            return render(request, self.template_name, {'form': form})

        archivo = form.cleaned_data['archivo']
        limpiar_antes = form.cleaned_data.get('limpiar_antes', False)

        if limpiar_antes:
            from etl_app.models import Direccion, Georeferencia
            count_eliminados = Lugar.objects.count()
            Lugar.objects.all().delete()  # Cascade elimina Direccion y Georeferencia
            ErrorImportacion.objects.filter(dataset='lugares').delete()
            logger.info(f"[Vista] BD de Lugares limpiada: {count_eliminados} registros eliminados.")
            messages.warning(
                request,
                f'Base de datos limpiada: {count_eliminados} lugares eliminados.'
            )

        try:
            upload_dir = Path(settings.MEDIA_ROOT) / 'uploads' / 'lugares'
            ruta_archivo = guardar_archivo_temporal(archivo, upload_dir)
        except Exception as e:
            logger.error(f"[Vista] Error al guardar archivo lugares: {e}")
            messages.error(request, f'Error al guardar el archivo: {e}')
            return render(request, self.template_name, {'form': form})

        try:
            from etl_app.services.lugares_etl import procesar_archivo_lugares
            resultado = procesar_archivo_lugares(ruta_archivo)

            request.session['resultado_etl'] = formatear_resultado_para_template(resultado)
            request.session['tipo_etl'] = 'lugares'

            messages.success(
                request,
                f'ETL completado: {resultado.insertados} lugares insertados, '
                f'{resultado.duplicados} duplicados omitidos, '
                f'{resultado.errores} errores.'
            )

            if resultado.sin_coordenadas > 0:
                messages.info(
                    request,
                    f'{resultado.sin_coordenadas} lugares sin coordenadas válidas '
                    f'(guardados sin georeferencia).'
                )

        except FileNotFoundError as e:
            messages.error(request, f'Archivo no encontrado: {e}')
            return render(request, self.template_name, {'form': form})
        except Exception as e:
            logger.error(f"[Vista] Error en ETL Lugares: {e}", exc_info=True)
            messages.error(request, f'Error durante el procesamiento ETL: {e}')
            return render(request, self.template_name, {'form': form})

        return redirect('etl_app:resultado')
    
# ══════════════════════════════════════════════════════════════
# SUBIDA Y PROCESAMIENTO — COMUNAS
# ══════════════════════════════════════════════════════════════

class UploadComunasView(View):
    """
    Vista para subir el archivo TXT de Comunas y ejecutar el ETL.
    """
    template_name = 'etl_app/upload_comunas.html'
    form_class = SubirComunasForm

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)

        if not form.is_valid():
            for field, errores in form.errors.items():
                for error in errores:
                    messages.error(request, f"Error en {field}: {error}")
            return render(request, self.template_name, {'form': form})

        archivo = form.cleaned_data['archivo']
        limpiar_antes = form.cleaned_data.get('limpiar_antes', False)

        if limpiar_antes:
            count_eliminados = Comuna.objects.count()
            Comuna.objects.all().delete()
            ErrorImportacion.objects.filter(dataset='comunas').delete()
            logger.info(f"[Vista] BD de Comunas limpiada: {count_eliminados} registros eliminados.")
            messages.warning(
                request,
                f'Base de datos limpiada: {count_eliminados} comunas eliminadas.'
            )

        try:
            upload_dir = Path(settings.MEDIA_ROOT) / 'uploads' / 'comunas'
            ruta_archivo = guardar_archivo_temporal(archivo, upload_dir)
        except Exception as e:
            logger.error(f"[Vista] Error al guardar archivo comunas: {e}")
            messages.error(request, f'Error al guardar el archivo: {e}')
            return render(request, self.template_name, {'form': form})

        try:
            # Importación dinámica del servicio ETL de comunas
            from etl_app.services.comunas_etl import ComunasETLService
            resultado = ComunasETLService(ruta_archivo).procesar()

            request.session['resultado_etl'] = formatear_resultado_para_template(resultado)
            request.session['tipo_etl'] = 'comunas'

            messages.success(
                request,
                f'ETL completado: {resultado.insertados} comunas insertadas, '
                f'{resultado.duplicados} duplicadas omitidas, '
                f'{resultado.errores} errores.'
            )

        except FileNotFoundError as e:
            messages.error(request, f'Archivo no encontrado: {e}')
            return render(request, self.template_name, {'form': form})
        except Exception as e:
            logger.error(f"[Vista] Error en ETL Comunas: {e}", exc_info=True)
            messages.error(request, f'Error durante el procesamiento ETL: {e}')
            return render(request, self.template_name, {'form': form})

        return redirect('etl_app:resultado')


# ══════════════════════════════════════════════════════════════
# VISTA DE RESULTADO
# ══════════════════════════════════════════════════════════════

class ResultadoView(TemplateView):
    """
    Muestra el resultado del último ETL ejecutado.
    Los datos vienen de la sesión de Django.
    """
    template_name = 'etl_app/resultado.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['resultado'] = self.request.session.get('resultado_etl', {})
        context['tipo_etl'] = self.request.session.get('tipo_etl', 'desconocido')
        return context


# ══════════════════════════════════════════════════════════════
# LISTAS DE DATOS
# ══════════════════════════════════════════════════════════════

class ListaFamososView(ListView):
    """
    Listado paginado de Famosos importados con filtros básicos.
    """
    model = Famoso
    template_name = 'etl_app/lista_famosos.html'
    context_object_name = 'famosos'
    paginate_by = 25
    ordering = ['nombre_completo']

    def get_queryset(self):
        qs = super().get_queryset()
        # Filtro por búsqueda
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(nombre_completo__icontains=q)
        # Filtro por fecha aproximada
        solo_aproximados = self.request.GET.get('aproximados', '')
        if solo_aproximados == '1':
            qs = qs.filter(es_fecha_aproximada=True)
        # Filtro cumpleaños
        solo_cumpleanos = self.request.GET.get('cumpleanos', '')
        if solo_cumpleanos == '1':
            qs = qs.filter(esta_de_cumpleanos=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['total'] = Famoso.objects.count()
        return context


class ListaLugaresView(ListView):
    """
    Listado paginado de Lugares importados.
    """
    model = Lugar
    template_name = 'etl_app/lista_lugares.html'
    context_object_name = 'lugares'
    paginate_by = 25
    ordering = ['nombre_lugar']

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'direccion', 'georeferencia'
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(nombre_lugar__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['total'] = Lugar.objects.count()
        return context


class ListaErroresView(ListView):
    """
    Listado de errores de importación.
    """
    model = ErrorImportacion
    template_name = 'etl_app/lista_errores.html'
    context_object_name = 'errores'
    paginate_by = 30
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        dataset = self.request.GET.get('dataset', '').strip()
        if dataset in ['famosos', 'lugares']:
            qs = qs.filter(dataset=dataset)
        tipo = self.request.GET.get('tipo', '').strip()
        if tipo:
            qs = qs.filter(tipo_error=tipo)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dataset_filter'] = self.request.GET.get('dataset', '')
        context['tipo_filter'] = self.request.GET.get('tipo', '')
        context['total_errores'] = ErrorImportacion.objects.count()
        return context

# ══════════════════════════════════════════════════════════════
# API ENDPOINTS (JSON)
# ══════════════════════════════════════════════════════════════

class ApiLugaresView(View):
    """
    Retorna el listado completo de lugares con sus coordenadas geográficas.
    Útil para renderizar mapas en el frontend (RF-19, RF-20).
    """
    def get(self, request, *args, **kwargs):
        lugares_georef = Lugar.objects.select_related('georeferencia').exclude(georeferencia__isnull=True)
        data = []
        for lugar in lugares_georef:
            data.append({
                'id': lugar.id,
                'nombre': lugar.nombre_lugar,
                'latitud': float(lugar.georeferencia.latitud),
                'longitud': float(lugar.georeferencia.longitud),
            })
        return JsonResponse({'lugares': data})


class ApiComunasSearchView(View):
    """
    Búsqueda inteligente optimizada (RF-11).
    - GET: Consulta localmente y en la API externa de forma volátil (sin insertar en BD).
    - POST: Registra de forma definitiva una comuna sólo cuando el usuario la selecciona.
    """
    
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        
        if not query:
            return JsonResponse({'resultados': [], 'api_resultados': [], 'sugerencias': []})
            
        # 1. Búsqueda por coincidencia parcial en la Base de Datos local
        resultados_locales = list(Comuna.objects.filter(nombre_normalizado__icontains=query).values('id', 'nombre_normalizado', 'region'))
        
        # Guardamos un set de nombres locales en minúsculas para no duplicar elementos en el dropdown
        nombres_locales = {c['nombre_normalizado'].lower() for c in resultados_locales}
        
        api_resultados = []
        sugerencias = []
        
        # 2. Si no hay coincidencias locales exactas perfectas, buscamos coincidencias en la API externa
        try:
            comunas_api = get_comunas_api() # Carga desde caché en memoria de tu external_apis.py
            if comunas_api:
                for c in comunas_api:
                    nombre_api = c.get("name") or c.get("nombre", "")
                    
                    # Si el texto buscado coincide con la comuna de la API
                    if query.lower() in nombre_api.lower():
                        # ¡CLAVE! Sólo la mostramos si NO existe ya guardada en la base de datos
                        if nombre_api.lower() not in nombres_locales:
                            region_api = c.get("region_name") or c.get("codigo_region", "Región Desconocida")
                            habitantes_api = c.get("population") or c.get("habitantes", None)
                            
                            # Evitamos duplicados en la lista de respuesta intermedia
                            if not any(a['nombre_normalizado'].lower() == nombre_api.lower() for a in api_resultados):
                                api_resultados.append({
                                    'nombre_normalizado': nombre_api,
                                    'region': region_api,
                                    'habitantes': habitantes_api
                                })
        except Exception as e:
            logger.error(f"[API Búsqueda] Error al leer la API remota: {e}")

        # 3. Si no hay nada local ni remoto, aplicamos búsqueda difusa tradicional
        if not resultados_locales and not api_resultados:
            todas_comunas = list(Comuna.objects.values_list('nombre_normalizado', flat=True))
            sugerencias_nombres = difflib.get_close_matches(query.title(), todas_comunas, n=5, cutoff=0.6)
            if sugerencias_nombres:
                sugerencias = list(Comuna.objects.filter(nombre_normalizado__in=sugerencias_nombres).values('id', 'nombre_normalizado', 'region'))
            
        # Retornamos las listas limpias. api_resultados contiene lo que está "en la nube" listo para ser seleccionado
        return JsonResponse({
            'resultados': resultados_locales,
            'api_resultados': api_resultados,
            'sugerencias': sugerencias
        })

    def post(self, request, *args, **kwargs):
        """
        Petición AJAX que se ejecuta ÚNICAMENTE al hacer clic en una sugerencia remota.
        Inserta la comuna con todos sus datos en la BD local de forma segura.
        """
        try:
            data = json.loads(request.body)
            nombre = data.get('nombre', '').strip()
            region = data.get('region', '').strip()
            habitantes = data.get('habitantes')
            
            if not nombre:
                return JsonResponse({'status': 'error', 'message': 'El nombre de la comuna es obligatorio.'}, status=400)
                
            # Guardamos físicamente en la BD duplicando el nombre en nombre_original
            comuna, created = Comuna.objects.update_or_create(
                nombre_normalizado=nombre,
                defaults={
                    'nombre_original': nombre,
                    'region': region,
                    'habitantes': habitantes
                }
            )
            
            logger.info(f"[API Selección] Comuna registrada exitosamente bajo demanda: {nombre} (Creada: {created})")
            return JsonResponse({'status': 'success', 'comuna_id': comuna.id, 'created': created})
            
        except Exception as e:
            logger.error(f"[API Selección] Error al insertar comuna seleccionada: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class ApiClearDBView(View):
    """
    Endpoint para eliminar todos los datos de la base de datos.
    Soporta POST (y DELETE) para realizar la limpieza.
    """
    def procesar_limpieza(self):
        from etl_app.models import Famoso, Lugar, Direccion, Georeferencia, Comuna, EjecucionETL, ErrorImportacion
        
        famosos_count, _ = Famoso.objects.all().delete()
        lugares_count, _ = Lugar.objects.all().delete()
        Direccion.objects.all().delete()
        Georeferencia.objects.all().delete()
        comunas_count, _ = Comuna.objects.all().delete()
        ejecuciones_count, _ = EjecucionETL.objects.all().delete()
        errores_count, _ = ErrorImportacion.objects.all().delete()
        
        return {
            'mensaje': 'Base de datos limpiada con éxito.',
            'eliminados': {
                'famosos': famosos_count,
                'lugares': lugares_count,
                'comunas': comunas_count,
                'ejecuciones': ejecuciones_count,
                'errores': errores_count
            }
        }

    def post(self, request, *args, **kwargs):
        res = self.procesar_limpieza()
        return JsonResponse(res)
        
    def delete(self, request, *args, **kwargs):
        res = self.procesar_limpieza()
        return JsonResponse(res)

# ══════════════════════════════════════════════════════════════
# LISTADO DE COMUNAS CON BÚSQUEDA INTERACTIVA
# ══════════════════════════════════════════════════════════════

class ListaComunasView(ListView):
    """
    Listado de Comunas con búsqueda interactiva.
    El endpoint API maneja las sugerencias en tiempo real.
    """
    model = Comuna
    template_name = 'etl_app/lista_comunas.html'
    context_object_name = 'comunas'
    paginate_by = 25
    ordering = ['nombre_normalizado']

    def get_queryset(self):
        qs = super().get_queryset()
        # Si viene un parámetro 'q' (búsqueda exacta), filtrar
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(nombre_normalizado__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['total'] = Comuna.objects.count()
        return context

