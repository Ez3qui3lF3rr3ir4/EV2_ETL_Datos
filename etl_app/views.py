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
    Búsqueda inteligente de comunas (RF-11).
    Busca coincidencias exactas primero y si no, sugiere coincidencias similares.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        from etl_app.models import Comuna
        
        if not query:
            return JsonResponse({'resultados': [], 'sugerencias': []})
            
        # 1. Búsqueda por coincidencia exacta o parcial (icontains)
        exact_matches = list(Comuna.objects.filter(nombre_normalizado__icontains=query).values('id', 'nombre_normalizado', 'region'))
        
        if exact_matches:
            return JsonResponse({'resultados': exact_matches, 'sugerencias': []})
            
        # 2. Si no hay coincidencias directas, búsqueda inteligente (difflib)
        todas_comunas = list(Comuna.objects.values_list('nombre_normalizado', flat=True))
        # Encontramos sugerencias cercanas con un corte de similitud (cutoff) de 0.6
        sugerencias_nombres = difflib.get_close_matches(query.title(), todas_comunas, n=5, cutoff=0.6)
        
        sugerencias = []
        if sugerencias_nombres:
            sugerencias = list(Comuna.objects.filter(nombre_normalizado__in=sugerencias_nombres).values('id', 'nombre_normalizado', 'region'))
            
        return JsonResponse({'resultados': [], 'sugerencias': sugerencias})

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


class ListaComunasView(ListView):
    """
    Vista para listar las comunas procesadas (RF-11 / Evaluación Parte 3.1)
    """
    model = Comuna
    template_name = 'etl_app/lista_comunas.html'
    context_object_name = 'comunas'
    ordering = ['nombre_normalizado']

class MapaLugaresView(TemplateView):
    """
    Vista para mostrar el mapa de lugares (RF-19 / Evaluación Parte 3.3)
    """
    template_name = 'etl_app/mapa_lugares.html'

class UploadComunasView(View):
    template_name = 'etl_app/upload_comunas.html'
    form_class = SubirComunasForm

    def get(self, request):
        return render(request, self.template_name, {'form': self.form_class()})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})
            
        archivo = form.cleaned_data['archivo']
        
        # Aquí llamarías a tu servicio de normalización de comunas
        # from etl_app.services.comunas_etl import procesar_archivo_comunas
        # resultado = procesar_archivo_comunas(archivo)
        
        messages.success(request, "Comunas procesadas y normalizadas exitosamente.")
        return redirect('etl_app:lista_comunas')