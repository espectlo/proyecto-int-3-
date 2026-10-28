import unittest
from decimal import Decimal

from apps.calificaciones.calculo import (
    ErrorCalculo,
    calcular_factores,
    validar_suma_factores,
)


class CalculoFactoresTests(unittest.TestCase):
    def test_ejemplo_de_referencia(self):
        montos = {
            8: 192770580,
            9: 64161878,
            10: 0,
            11: 111812860,
            20: 71298705,
            28: 15837333,
        }
        factores = calcular_factores(montos)
        self.assertEqual(factores[8], Decimal("0.52277431"))
        self.assertEqual(factores[9], Decimal("0.17400052"))
        self.assertEqual(factores[11], Decimal("0.30322517"))
        self.assertEqual(factores[20], Decimal("0.19335488"))
        self.assertEqual(factores[28], Decimal("0.04294924"))

    def test_denominador_cero_se_rechaza(self):
        with self.assertRaisesRegex(ErrorCalculo, "suma de los montos base es cero"):
            calcular_factores({})

    def test_monto_negativo_se_rechaza(self):
        with self.assertRaisesRegex(ErrorCalculo, "no negativo"):
            calcular_factores({8: -1, 9: 1})

    def test_factor_mayor_que_uno_se_rechaza(self):
        with self.assertRaisesRegex(ErrorCalculo, "mayores que 1"):
            calcular_factores({8: 1, 20: 2})

    def test_suma_de_8_a_16_no_puede_superar_uno(self):
        factores = {
            8: Decimal("0.60000000"),
            9: Decimal("0.40000001"),
        }
        with self.assertRaisesRegex(ErrorCalculo, "no puede superar 1"):
            validar_suma_factores(factores)

    def test_suma_igual_a_uno_es_valida(self):
        total = validar_suma_factores(
            {8: Decimal("0.40000000"), 9: Decimal("0.60000000")}
        )
        self.assertEqual(total, Decimal("1.00000000"))

    def test_valida_factores_fuera_del_rango_de_suma(self):
        with self.assertRaisesRegex(ErrorCalculo, "columna 20"):
            validar_suma_factores({8: Decimal("0.5"), 20: Decimal("1.1")})


if __name__ == "__main__":
    unittest.main()
