"""
tests.py — Pruebas unitarias para etl_app.
"""

from datetime import date
from django.test import TestCase

from etl_app.services.parsers import parse_linea_famoso, parse_linea_lugar, es_header_lugares
from etl_app.services.normalizers import (
    normalizar_nombre, normalizar_fecha,
    normalizar_direccion, normalizar_coordenadas
)
from etl_app.services.deduplicator import generar_hash_famoso, generar_hash_lugar
from etl_app.services.validators import validar_nombre, validar_coordenadas


class TestFamososETL(TestCase):
    
    def test_parser_famoso_formato_normal(self):
        linea = "1. William Shakespeare - 1564/04/23"
        res = parse_linea_famoso(linea)
        self.assertEqual(res['numero'], 1)
        self.assertEqual(res['nombre_raw'], "William Shakespeare")
        self.assertEqual(res['fecha_raw'], "1564/04/23")

    def test_parser_famoso_sin_numero(self):
        linea = "Albert Einstein - 1879-03-14"
        res = parse_linea_famoso(linea)
        self.assertEqual(res['nombre_raw'], "Albert Einstein")
        self.assertEqual(res['fecha_raw'], "1879-03-14")

    def test_normalizar_fechas_validas(self):
        # YYYY/MM/DD
        d, aprox, fmt = normalizar_fecha("1564/04/23")
        self.assertEqual(d, date(1564, 4, 23))
        self.assertFalse(aprox)
        self.assertEqual(fmt, "23-04-1564")
        
        # DD-MM-YYYY
        d, aprox, fmt = normalizar_fecha("24-07-1897")
        self.assertEqual(d, date(1897, 7, 24))

    def test_normalizar_fechas_historicas(self):
        # Fecha aproximada
        d, aprox, fmt = normalizar_fecha("alrededor del 69 a.C.")
        self.assertIsNone(d)
        self.assertTrue(aprox)
        
        d, aprox, fmt = normalizar_fecha("alrededor de 1028")
        self.assertIsNone(d)
        self.assertTrue(aprox)

    def test_deduplicador_hashes_famoso(self):
        h1 = generar_hash_famoso("albert einstein", "1879-03-14")
        h2 = generar_hash_famoso("Albert Einstein", "1879-03-14")
        self.assertEqual(h1, h2)
        
        # Mismo nombre, distinta fecha en TXT -> distinto hash exacto
        h3 = generar_hash_famoso("Albert Einstein", "1879/03/14")
        self.assertNotEqual(h1, h3)


class TestLugaresETL(TestCase):
    
    def test_es_header(self):
        self.assertTrue(es_header_lugares("Nombre del lugar;Dirección Completa;Georeferencia"))
        self.assertFalse(es_header_lugares("Googleplex;1600 Amphitheatre Parkway;37.4, -122.0"))

    def test_parser_lugar(self):
        linea = "Googleplex;1600 Amphitheatre Parkway, Mountain View, CA 94043, USA;37.422, -122.084"
        res = parse_linea_lugar(linea)
        self.assertEqual(res['nombre_raw'], "Googleplex")
        self.assertTrue(res['direccion_raw'].startswith("1600"))
        self.assertEqual(res['georef_raw'], "37.422, -122.084")

    def test_normalizar_coordenadas(self):
        coords = normalizar_coordenadas("37.422, -122.084")
        self.assertIsNotNone(coords)
        self.assertEqual(float(coords[0]), 37.422)
        self.assertEqual(float(coords[1]), -122.084)
        
        # Coordenadas inválidas
        self.assertIsNone(normalizar_coordenadas("900, 100"))
        self.assertIsNone(normalizar_coordenadas("texto, texto"))

    def test_validadores_negocio(self):
        # Nombres
        self.assertTrue(validar_nombre("Googleplex")[0])
        self.assertFalse(validar_nombre("")[0])
        self.assertFalse(validar_nombre("A")[0])
        
        # Coordenadas
        self.assertTrue(validar_coordenadas(0, 0)[0])
        self.assertFalse(validar_coordenadas(91, 0)[0])
        self.assertFalse(validar_coordenadas(0, 181)[0])
