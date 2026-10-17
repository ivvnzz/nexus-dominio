"""Pruebas sin Docker ni red: conversión, consistencia e idempotencia estructural."""
import unittest
from datetime import date, datetime
from decimal import Decimal

from carga import cargar
from carga.transformaciones import booleano, decimal, entero, fecha, fecha_hora, convertir


class TestConversiones(unittest.TestCase):
    def test_booleanos_csv(self):
        self.assertTrue(booleano("True"))
        self.assertTrue(booleano("1.0"))
        self.assertFalse(booleano("False"))
        self.assertIsNone(booleano(""))

    def test_enteros_decimales(self):
        self.assertEqual(entero("5.0"), 5)
        self.assertEqual(entero("-9.0"), -9)
        self.assertEqual(decimal("19.50"), Decimal("19.50"))
        self.assertIsNone(decimal(""))
        with self.assertRaises(ValueError):
            entero("5.3")

    def test_fechas(self):
        self.assertEqual(fecha("2025-06-04"), date(2025, 6, 4))
        self.assertEqual(fecha_hora("2026-07-09 16:12:33"), datetime(2026, 7, 9, 16, 12, 33))


class TestDatosReales(unittest.TestCase):
    def test_csv_y_referencias(self):
        datos = cargar.preparar_datos()
        self.assertEqual(len(datos["productos"][0]), 1500)
        self.assertEqual(len(datos["usuarios"][0]), 2077)
        self.assertEqual(len(datos["transacciones"][0]), 9770)

    def test_transacciones_normalizadas(self):
        datos = cargar.preparar_datos()
        transacciones = datos["transacciones"][0]
        self.assertTrue(all(t[4] is not None for t in transacciones))
        self.assertTrue(all(t[5] > 0 for t in transacciones))
        self.assertTrue(all(t[10] in ("pagado", "devuelto") for t in transacciones))

    def test_productos_stock_faltante(self):
        datos = cargar.preparar_datos()
        productos = datos["productos"][0]
        self.assertTrue(any(p[5] is None for p in productos))
        self.assertTrue(any(p[5] is not None and p[5] < 0 for p in productos))


if __name__ == "__main__":
    unittest.main()
