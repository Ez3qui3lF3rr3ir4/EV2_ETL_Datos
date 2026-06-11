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
                    "habitantes": c.get("population") or c.get("habitantes"),
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
    Busca la imagen del famoso en Wikipedia de forma inteligente.
    1. Intenta búsqueda directa por título (evita que 'Coco Chanel' devuelva la tienda 'Chanel').
    2. Si falla, busca por texto completo respetando estrictamente el orden de relevancia.
    """
    def consultar_wikipedia(lang, nombre):
        url = f"https://{lang}.wikipedia.org/w/api.php"
        headers = {
            "User-Agent": "EV2_ETL_App/1.0 (contacto@tu_dominio.com; Bot de Aprendizaje Informatica)"
        }

        # ══════════════════════════════════════════════════════════════
        # PASO 1: INTENTO DIRECTO POR TÍTULO EXACTO (Evita cruces con marcas)
        # ══════════════════════════════════════════════════════════════
        params_directo = {
            "action": "query",
            "titles": nombre,
            "prop": "pageimages",
            "redirects": 1,  # <--- CLAVE: Sigue redirecciones automáticas a la persona real
            "format": "json",
            "pithumbsize": 800
        }
        
        try:
            response = requests.get(url, params=params_directo, headers=headers, timeout=5)
            if response.status_code == 200:
                pages = response.json().get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    # Si el artículo existe y tiene imagen, la retornamos de inmediato
                    if page_id != "-1" and "thumbnail" in page_info:
                        logger.info(f"[Wikipedia {lang} - Directo] Imagen exacta encontrada para '{nombre}'")
                        return {
                            "url": page_info["thumbnail"]["source"],
                            "fuente": f"Wikipedia ({lang})",
                            "fecha": date.today().isoformat()
                        }
        except Exception as e:
            logger.warning(f"Error en búsqueda directa Wikipedia ({lang}) para {nombre}: {e}")

        # ══════════════════════════════════════════════════════════════
        # PASO 2: FALLBACK A BÚSQUEDA POR TEXTO (Si el nombre varía un poco)
        # ══════════════════════════════════════════════════════════════
        params_buscar = {
            "action": "query",
            "generator": "search",
            "gsrsearch": nombre,
            "gsrlimit": 5,
            "prop": "pageimages",
            "format": "json",
            "pithumbsize": 800
        }
        
        try:
            response = requests.get(url, params=params_buscar, headers=headers, timeout=5)
            if response.status_code == 200:
                pages = response.json().get("query", {}).get("pages", {})
                
                # ¡SOLUCIÓN CRUCIAL!: Convertimos el dict a una lista y la ordenamos 
                # estrictamente por el 'index' de relevancia que entrega Wikipedia.
                paginas_ordenadas = sorted(
                    [p for p in pages.values() if isinstance(p, dict)],
                    key=lambda x: x.get("index", 99)
                )
                
                for page_info in paginas_ordenadas:
                    title = page_info.get("title", "").lower()
                    page_id = str(page_info.get("pageid", "-1"))
                    
                    # Omitir páginas de desambiguación obvias
                    if "desambiguación" in title or "disambiguation" in title:
                        continue
                        
                    if page_id != "-1" and "thumbnail" in page_info:
                        logger.info(f"[Wikipedia {lang} - Buscador] Imagen encontrada por relevancia para '{nombre}' en artículo: '{page_info.get('title')}'")
                        return {
                            "url": page_info["thumbnail"]["source"],
                            "fuente": f"Wikipedia ({lang})",
                            "fecha": date.today().isoformat()
                        }
        except Exception as e:
            logger.warning(f"Error en buscador general Wikipedia ({lang}) para {nombre}: {e}")
            
        return None

    # Primero intentar todo en Español
    resultado = consultar_wikipedia("es", nombre_famoso)
    if resultado:
        return resultado
        
    # Si no dio frutos, intentar en Inglés
    return consultar_wikipedia("en", nombre_famoso)

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
