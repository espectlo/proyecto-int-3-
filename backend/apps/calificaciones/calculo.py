import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping


PRECISION = Decimal("0.00000001")
COLUMNAS_FACTOR = range(8, 38)
BASE_DESDE = int(os.getenv("FACTOR_BASE_START", "8"))
BASE_HASTA = int(os.getenv("FACTOR_BASE_END", "19"))
VALIDACION_DESDE = int(os.getenv("FACTOR_SUM_START", "8"))
VALIDACION_HASTA = int(os.getenv("FACTOR_SUM_END", "16"))


class ErrorCalculo(ValueError):
    pass


def calcular_factores(
    montos: Mapping[int, Decimal | int | str],
    base_desde: int = BASE_DESDE,
    base_hasta: int = BASE_HASTA,
) -> dict[int, Decimal]:
    if (
        base_desde > base_hasta
        or base_desde < COLUMNAS_FACTOR.start
        or base_hasta >= COLUMNAS_FACTOR.stop
    ):
        raise ErrorCalculo("El rango de la base de cálculo no es válido.")

    valores: dict[int, Decimal] = {}
    for columna in COLUMNAS_FACTOR:
        try:
            valor = Decimal(str(montos.get(columna, 0)))
        except (InvalidOperation, ValueError):
            raise ErrorCalculo(
                f"El monto de la columna {columna} no es válido."
            ) from None
        if not valor.is_finite() or valor < 0:
            raise ErrorCalculo(
                f"El monto de la columna {columna} debe ser no negativo."
            )
        valores[columna] = valor

    denominador = sum(
        (valores[columna] for columna in range(base_desde, base_hasta + 1)),
        Decimal("0"),
    )
    if denominador == 0:
        raise ErrorCalculo("La suma de los montos base es cero; no se puede calcular.")

    factores = {
        columna: (monto / denominador).quantize(
            PRECISION, rounding=ROUND_HALF_UP
        )
        for columna, monto in valores.items()
    }
    fuera_de_rango = [
        columna
        for columna, factor in factores.items()
        if factor < 0 or factor > 1
    ]
    if fuera_de_rango:
        columnas = ", ".join(str(columna) for columna in fuera_de_rango)
        raise ErrorCalculo(
            f"El cálculo produce factores mayores que 1 en las columnas: {columnas}."
        )
    return factores


def validar_suma_factores(
    factores: Mapping[int, Decimal | int | str],
    desde: int = VALIDACION_DESDE,
    hasta: int = VALIDACION_HASTA,
) -> Decimal:
    if (
        desde > hasta
        or desde < COLUMNAS_FACTOR.start
        or hasta >= COLUMNAS_FACTOR.stop
    ):
        raise ErrorCalculo("El rango de validación no es válido.")

    valores: dict[int, Decimal] = {}
    for columna in COLUMNAS_FACTOR:
        try:
            valor = Decimal(str(factores.get(columna, 0)))
        except (InvalidOperation, ValueError):
            raise ErrorCalculo(
                f"El factor de la columna {columna} no es válido."
            ) from None
        if not valor.is_finite() or valor < 0 or valor > 1:
            raise ErrorCalculo(
                f"El factor de la columna {columna} debe estar entre 0 y 1."
            )
        valores[columna] = valor

    total = Decimal("0")
    for columna in range(desde, hasta + 1):
        total += valores[columna]
    total = total.quantize(PRECISION, rounding=ROUND_HALF_UP)
    if total > 1:
        raise ErrorCalculo("La suma de los factores configurados no puede superar 1.")
    return total
