<<<<<<< HEAD
# Proyecto ETL — ArquitecturaDeDatos EV2 P2

Breve: aplicación Django para procesar dos datasets TXT (Famosos y Lugares) y almacenar resultados en la base de datos.

**Prerequisitos**
- Python 3.8+ (recomendado 3.10+)
- Git
- Opcional: una base de datos (por defecto SQLite funciona sin configuración adicional)

**Instalación local (Windows)**
1. Clona el repositorio y sitúate en la raíz del proyecto:

```bash
git clone <tu-repo.git>
cd ArquitecturaDeDatos_EV2_P2
```

2. Crea y activa un entorno virtual:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -U pip
```

3. Instalación de dependencias:

- Si existe `requirements.txt`:

```bash
pip install -r requirements.txt
```

- Si no existe, al menos instala Django (versión mínima requerida por el proyecto):

```bash
pip install Django
```

**Configuración mínima**
- Por defecto el proyecto usa SQLite. Si quieres usar otra BD, configura `DATABASES` en `manage.py`/`settings.py` o usa variables de entorno según tu flujo.
- Asegúrate de que exista la carpeta `media/uploads` (ya incluida en el repo). Si no, créala:

```bash
mkdir -p media\\uploads\\famosos media\\uploads\\lugares
```

**Migraciones y superusuario**

```bash
python manage.py migrate
python manage.py createsuperuser
```

**Cargar los datasets**
- En la raíz del repositorio hay dos archivos de ejemplo: `DATOS2026-2.txt` y `DATOS2026-3.TXT`.
- Importarlos con los comandos de management incluidos:

```bash
python manage.py import_famosos DATOS2026-2.txt
python manage.py import_lugares DATOS2026-3.TXT
```

- Opciones útiles:
  - `--limpiar`  → elimina registros existentes antes de importar
  - `--dry-run`  → procesa sin guardar nada (útil para validar formato)

**Ejecutar servidor de desarrollo**

```bash
python manage.py runserver
```

Abre http://127.0.0.1:8000/ para ver la aplicación. El admin está en `/admin`.

**Tests**

```bash
python manage.py test
```

**Notas y recomendaciones antes de subir a GitHub**
- Añade un `.gitignore` que excluya entornos virtuales, archivos sensibles y medias:

```
.venv/
__pycache__/
*.pyc
db.sqlite3
media/
logs/
```

- Los archivos `DATOS2026-2.txt` y `DATOS2026-3.TXT` pueden contener codificaciones mixtas (UTF-8 / latin-1). Los importadores incluyen manejo de encodings, pero si subes los archivos al repositorio, considera normalizarlos o documentar su encoding.
- Para producción, configura `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` y una base de datos robusta (Postgres). Ejecuta `collectstatic` y configura un servidor WSGI/ASGI adecuado.

**Comandos útiles resumen**

```bash
# activar venv (Windows)
.venv\\Scripts\\activate

# instalar dependencias
pip install -r requirements.txt

# migrar y crear admin
python manage.py migrate
python manage.py createsuperuser

# importar datasets
python manage.py import_famosos DATOS2026-2.txt
python manage.py import_lugares DATOS2026-3.TXT

# iniciar servidor
python manage.py runserver
```

Si quieres, puedo:
- crear un `.gitignore` inicial en el repo, o
- añadir un `requirements.txt` generado desde mi entorno, o
- abrir un PR con correcciones sugeridas al código ETL.

---
=======
# EV2_ETL_Datos
>>>>>>> 35e3632086a5f6bf1ee0c8f499cf9090d893dc84
