"""
urls.py — URLs de la aplicación etl_app.

Namespace: etl_app
"""

from django.urls import path
from etl_app import views

app_name = 'etl_app'

urlpatterns = [
    # Página principal — resumen de BD
    path('', views.IndexView.as_view(), name='index'),

    # ETL Famosos
    path('famosos/upload/', views.UploadFamososView.as_view(), name='upload_famosos'),
    path('famosos/', views.ListaFamososView.as_view(), name='lista_famosos'),

    # ETL Lugares
    path('lugares/upload/', views.UploadLugaresView.as_view(), name='upload_lugares'),
    path('lugares/', views.ListaLugaresView.as_view(), name='lista_lugares'),
    path('lugares/mapa/', views.MapaLugaresView.as_view(), name='mapa_lugares'),

    #ETL Comunas

    path('comunas/', views.ListaComunasView.as_view(), name='lista_comunas'),
    path('upload/comunas/', views.UploadComunasView.as_view(), name='upload_comunas'),

    # Resultado del último ETL
    path('resultado/', views.ResultadoView.as_view(), name='resultado'),

    # Errores de importación
    path('errores/', views.ListaErroresView.as_view(), name='lista_errores'),

    # API Endpoints (RF-11, RF-19, RF-20)
    path('api/lugares/', views.ApiLugaresView.as_view(), name='api_lugares'),
    path('api/comunas/search/', views.ApiComunasSearchView.as_view(), name='api_comunas_search'),
    path('api/clear-db/', views.ApiClearDBView.as_view(), name='api_clear_db'),
]
