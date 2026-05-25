"""
urls.py — URLs raíz del proyecto datos_proyecto.
Incluye las URLs de etl_app y sirve archivos media durante desarrollo.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Panel de administración Django
    path('admin/', admin.site.urls),
    # Todas las URLs de la app ETL (raíz del sitio)
    path('', include('etl_app.urls')),
]

# Servir archivos media solo en modo DEBUG (desarrollo local)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
