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

    # Resultado del último ETL
    path('resultado/', views.ResultadoView.as_view(), name='resultado'),

    # Errores de importación
    path('errores/', views.ListaErroresView.as_view(), name='lista_errores'),
]
