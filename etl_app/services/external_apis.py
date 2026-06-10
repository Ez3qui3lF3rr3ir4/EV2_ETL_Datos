import requests
import logging
from datetime import date
from etl_app.services.normalizers import normalizar_comuna_busqueda

logger = logging.getLogger('etl_app')

_COMUNAS_CACHE = None

def get_comunas_fallback():
    """Descarga un JSON alternativo público de comunas de Chile si el DPA falla."""
    url = "https://raw.githubusercontent.com/climoralesg/api-regiones-provincias-comunas-Chile/master/territoriochile.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            datos = response.json()
            comunas_planas = []
            for region in datos:
                nombre_region = region.get("nombre", "Región Desconocida")
                for provincia in region.get("provincias", []):
                    for comuna in provincia.get("comunas", []):
                        comunas_planas.append({
                            "nombre": comuna.get("nombre"),
                            "codigo_region": nombre_region,
                        })
            return comunas_planas
    except Exception as e:
        logger.warning(f"Falló el repositorio de fallback en Github: {e}")
    return []

def get_comunas_api():
    """Obtiene la lista de comunas desde la API de ChileAbierto, usando caché local."""
    global _COMUNAS_CACHE
    if _COMUNAS_CACHE is None:
        url = "https://chileabierto.cl/api/v1/comunas"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                _COMUNAS_CACHE = response.json().get('data', [])
                logger.info(f"API ChileAbierto cargada exitosamente: {len(_COMUNAS_CACHE)} comunas encontradas.")
                return _COMUNAS_CACHE
            else:
                logger.warning(f"Error HTTP al consultar API ChileAbierto: {response.status_code}")
        except Exception as e:
            logger.warning(f"No se pudo conectar a la API ChileAbierto: {e}")
        
        logger.info("Intentando usar repositorio de fallback en Github para comunas...")
        fallback_data = get_comunas_fallback()
        if fallback_data:
            _COMUNAS_CACHE = fallback_data
            logger.info(f"Fallback cargado exitosamente: {len(_COMUNAS_CACHE)} comunas encontradas.")
        else:
            _COMUNAS_CACHE = []
            
    return _COMUNAS_CACHE

def fetch_comuna_info(nombre_comuna_raw):
    """
    Valida la comuna contra la API oficial.
    Retorna un diccionario con 'nombre_oficial', 'region' y 'habitantes' si existe, o None si no es válida.
    Si la API está caída, retorna un fallback asumiendo que es válida.
    """
    comunas_api = get_comunas_api()
    nombre_busqueda = normalizar_comuna_busqueda(nombre_comuna_raw)
    
    if comunas_api:
        for c in comunas_api:
            nombre_api = c.get("name") or c.get("nombre", "")
            if normalizar_comuna_busqueda(nombre_api) == nombre_busqueda:
                # Comuna oficial encontrada
                return {
                    "nombre_oficial": nombre_api,
                    "region": c.get("region_name") or c.get("codigo_region", "Región Desconocida"),
                    "habitantes": c.get("population")
                }
        
        # La API respondió correctamente, pero la comuna no se encontró (es inválida)
        return None
    
    # Fallback si la API está caída (se asume válida, con el nombre lo más limpio posible)
    return {
        "nombre_oficial": " ".join(nombre_comuna_raw.title().split()),
        "region": "Región Desconocida (Offline)",
        "habitantes": None
    }

def fetch_famoso_image(nombre_famoso):
    """
    Busca la imagen del famoso usando MediaWiki Action API (Wikipedia).
    Utiliza el motor de búsqueda evaluando múltiples resultados para evitar falsos negativos.
    Intenta primero en Wikipedia en español, y si no encuentra imagen, busca en Wikipedia en inglés.
    """
    def buscar_en_wikipedia(lang, nombre):
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": nombre,
            "gsrlimit": 5,         # <--- SOLUCIÓN 1: Evaluamos los primeros 5 resultados, no solo uno
            "prop": "pageimages",
            "format": "json",
            "pithumbsize": 800
        }
        try:
            # SOLUCIÓN 3: Identificamos correctamente el bot según las políticas de Wikimedia para evitar bloqueos por ráfagas
            headers = {
                "User-Agent": "EV2_ETL_App/1.0 (contacto@tu_dominio_o_correo.com; Bot de Aprendizaje Informatica)"
            }
            response = requests.get(url, params=params, timeout=5, headers=headers)
            if response.status_code == 200:
                data = response.json()
                pages = data.get("query", {}).get("pages", {})
                
                # SOLUCIÓN 2: Recorremos los resultados candidatos buscando el primero con foto válida
                for page_id, page_info in pages.items():
                    title = page_info.get("title", "").lower()
                    
                    # Filtro opcional: Saltar páginas que explícitamente son de desambiguación
                    if "desambiguación" in title or "disambiguation" in title:
                        continue
                        
                    if page_id != "-1" and "thumbnail" in page_info:
                        logger.info(f"[Wikipedia {lang}] Imagen encontrada con éxito para '{nombre}' en artículo: '{page_info.get('title')}'")
                        return {
                            "url": page_info["thumbnail"]["source"],
                            "fuente": f"Wikipedia ({lang})",
                            "fecha": date.today().isoformat()
                        }
        except Exception as e:
            logger.warning(f"Error consultando imagen en Wikipedia ({lang}) para {nombre}: {e}")
        return None

    # Primero intentar en español
    resultado = buscar_en_wikipedia("es", nombre_famoso)
    if resultado:
        return resultado
        
    # Fallback a inglés
    return buscar_en_wikipedia("en", nombre_famoso)

def geocode_lugar(nombre_lugar):
    """
    Busca coordenadas usando Nominatim (OpenStreetMap).
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": nombre_lugar,
        "format": "json",
        "limit": 1
    }
    
    try:
        # Nominatim requiere User-Agent descriptivo
        headers = {"User-Agent": "EV2_ETL_App/1.0 (contacto@ejemplo.com)"}
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                return {
                    "latitud": data[0]["lat"],
                    "longitud": data[0]["lon"]
                }
    except Exception as e:
        logger.warning(f"Error geocodificando {nombre_lugar}: {e}")
        
    return None
