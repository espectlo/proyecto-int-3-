from django.core.management.base import BaseCommand

from apps.calificaciones.models import (
    ColumnaTributaria,
    Mercado,
    OrigenInformacion,
)
from apps.cuentas.models import Rol


COLUMNAS = {
    8: "Con crédito por IDPC generados a contar del 01.01.2017",
    9: "Con crédito por IDPC acumulados hasta el 31.12.2016",
    10: "Con derecho a crédito por pago de IDPC voluntario",
    11: "Sin derecho a crédito",
    12: "Rentas provenientes del registro RAP y Diferencia Inicial ex Art. 14 TER A)",
    13: "Otras rentas percibidas sin prioridad en su orden de imputación",
    14: "Exceso Distribuciones Desproporcionadas (N° 9 Art. 14 A)",
    15: "Utilidades afectadas con impuesto sustitutivo al FUT (ISFUT) Ley 20.780",
    16: "Rentas generadas hasta el 31.12.1983 y/o utilidades afectadas con ISFUT",
    17: "Rentas Exentas de IGC (Art. 11, Ley 18.401), afectas a Impuesto Adicional",
    18: "Rentas Exentas de IGC y/o Impuesto Adicional (IA)",
    19: "Ingresos No Constitutivos de Renta",
    20: "No sujetos a restitución hasta 31.12.2019 sin derecho",
    21: "No sujetos a restitución hasta 31.12.2019 con derecho",
    22: "No sujetos a restitución desde 01.01.2020 sin derecho",
    23: "No sujetos a restitución desde 01.01.2020 con derecho",
    24: "Sujeto a restitución sin derecho",
    25: "Sujeto a restitución con derecho",
    26: "Sujeto a restitución sin derecho (pendiente de confirmar duplicidad)",
    27: "Sujeto a restitución con derecho (pendiente de confirmar duplicidad)",
    28: "Crédito IPE",
    29: "Asociados a Rentas Afectas, sin derecho",
    30: "Asociados a Rentas Afectas, con derecho",
    31: "Asociados a Rentas Exentas (artículo 11, Ley 18.401), sin derecho",
    32: "Asociados a Rentas Exentas (artículo 11, Ley 18.401), con derecho",
    33: "Crédito por IPE",
    34: "Crédito por impuesto tasa adicional, Ex. Art. 21 LIR",
    35: "Tasa Efectiva del Crédito del FUT (TEF)",
    36: "Tasa Efectiva del Crédito del FUNT (TEX)",
    37: "Devolución de capital Art. 17 N° 7 LIR",
}

TIPOS_COLUMNAS = {
    35: ColumnaTributaria.TipoDato.TASA,
    36: ColumnaTributaria.TipoDato.TASA,
}

FORMULAS_COLUMNAS = {
    34: "Monto / SUMA(Montos 8..19) (provisional)",
    35: "Tasa ingresada directamente; sin fórmula (provisional)",
    36: "Tasa ingresada directamente; sin fórmula (provisional)",
    37: "Monto / SUMA(Montos 8..19) (provisional)",
}

MERCADOS = [
    ("ACN", "Acciones"),
    ("CFI", "Fondos de inversión (CFI)"),
    ("FMU", "Fondos mutuos"),
]

ROLES = [
    ("CORREDOR", "Corredor", "Acceso local a calificaciones de su corredora."),
    (
        "OPERADOR_BOLSA",
        "Operador de Bolsa",
        "Gestiona calificaciones generales de la Bolsa.",
    ),
    (
        "ADMINISTRADOR",
        "Administrador",
        "Administra usuarios y consulta auditoría.",
    ),
    ("AUDITOR", "Auditor", "Acceso de solo lectura y revisión de auditoría."),
]

ORIGENES = [
    ("ARCHIVO_CARGA", "Archivo de carga"),
    ("INGRESO_MANUAL", "Ingreso manual"),
    ("SISTEMA", "Sistema"),
]


class Command(BaseCommand):
    help = "Crea o actualiza los roles y catálogos tributarios iniciales."

    def handle(self, *args, **options):
        for codigo, nombre, descripcion in ROLES:
            Rol.objects.update_or_create(
                codigo=codigo,
                defaults={"nombre": nombre, "descripcion": descripcion},
            )

        for codigo, nombre in MERCADOS:
            Mercado.objects.update_or_create(
                codigo=codigo, defaults={"nombre": nombre, "activo": True}
            )

        for codigo, descripcion in ORIGENES:
            OrigenInformacion.objects.update_or_create(
                codigo=codigo, defaults={"descripcion": descripcion}
            )

        for nro_columna in range(8, 38):
            nombre = COLUMNAS.get(
                nro_columna,
                f"Columna {nro_columna} (pendiente de homologar)",
            )
            formula = FORMULAS_COLUMNAS.get(
                nro_columna,
                f"Monto {nro_columna} / SUMA(Montos 8..19)",
            )
            tipo_dato = TIPOS_COLUMNAS.get(
                nro_columna,
                ColumnaTributaria.TipoDato.MONTO,
            )
            ColumnaTributaria.objects.get_or_create(
                nro_columna=nro_columna,
                defaults={
                    "nombre_homologado": nombre,
                    "tipo_dato": tipo_dato,
                    "grupo": (
                        "Montos base"
                        if nro_columna <= 19
                        else "Montos complementarios"
                    ),
                    "formula": formula,
                    "pendiente_homologacion": False,
                    "reglas_provisionales": nro_columna >= 34,
                    "activa": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Catálogos listos: 4 roles, 3 mercados, 3 orígenes y 30 columnas."
            )
        )
