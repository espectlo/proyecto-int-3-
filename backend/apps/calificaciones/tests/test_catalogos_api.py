from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.calificaciones.calculo import calcular_factores
from apps.calificaciones.models import ColumnaTributaria, LogAuditoria
from apps.cuentas.models import Rol, Usuario


class CatalogoTributarioApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sembrar_catalogos", verbosity=0)
        cls.rol_admin = Rol.objects.get(codigo=Rol.Codigo.ADMINISTRADOR)
        cls.rol_operador = Rol.objects.get(codigo=Rol.Codigo.OPERADOR_BOLSA)
        cls.admin = cls.crear_usuario("admin-catalogo@example.test", cls.rol_admin)
        cls.operador = cls.crear_usuario(
            "operador-catalogo@example.test",
            cls.rol_operador,
        )

    @classmethod
    def crear_usuario(cls, email, rol):
        cuenta = get_user_model().objects.create_user(
            username=email,
            email=email,
            password="Clave-segura-1234!",
        )
        return Usuario.objects.create(cuenta=cuenta, email=email, rol=rol)

    @staticmethod
    def cliente(perfil):
        cliente = APIClient()
        cliente.force_authenticate(user=perfil.cuenta)
        return cliente

    def test_catalogo_expone_nombres_y_reglas_provisionales_homologadas(self):
        response = self.cliente(self.operador).get("/api/v1/catalogos/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        columnas = {
            columna["nro_columna"]: columna
            for columna in response.data["columnas_tributarias"]
        }
        self.assertEqual(
            columnas[34]["nombre_homologado"],
            "Crédito por impuesto tasa adicional, Ex. Art. 21 LIR",
        )
        self.assertEqual(columnas[34]["tipo_dato"], "MONTO")
        self.assertEqual(
            columnas[34]["formula"],
            "Monto / SUMA(Montos 8..19) (provisional)",
        )
        self.assertEqual(columnas[35]["tipo_dato"], "TASA")
        self.assertEqual(columnas[36]["tipo_dato"], "TASA")
        self.assertEqual(columnas[37]["tipo_dato"], "MONTO")
        self.assertTrue(all(columnas[n]["reglas_provisionales"] for n in range(34, 38)))

    def test_administrador_edita_metadatos_y_se_audita_sin_cambiar_calculos(self):
        factores_antes = calcular_factores(
            {8: 10, 34: 5, 35: 2, 36: 3, 37: 4}
        )
        columna = ColumnaTributaria.objects.get(pk=35)
        response = self.cliente(self.admin).patch(
            f"/api/v1/catalogos/columnas/{columna.pk}/",
            {
                "nombre_homologado": "Nombre confirmado",
                "tipo_dato": "MONTO",
                "formula": "Nueva regla descriptiva",
                "reglas_provisionales": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        columna.refresh_from_db()
        self.assertEqual(columna.nombre_homologado, "Nombre confirmado")
        self.assertEqual(columna.tipo_dato, ColumnaTributaria.TipoDato.MONTO)
        self.assertEqual(columna.formula, "Nueva regla descriptiva")
        self.assertFalse(columna.reglas_provisionales)
        evento = LogAuditoria.objects.get(
            entidad="ColumnaTributaria",
            id_registro=columna.pk,
        )
        self.assertEqual(evento.valor_anterior["tipo_dato"], "TASA")
        self.assertEqual(evento.valor_nuevo["tipo_dato"], "MONTO")
        self.assertEqual(evento.metodo, "ACTUALIZAR_CATALOGO")
        self.assertEqual(
            calcular_factores({8: 10, 34: 5, 35: 2, 36: 3, 37: 4}),
            factores_antes,
        )

    def test_catalogo_no_administrador_no_puede_editar(self):
        response = self.cliente(self.operador).patch(
            "/api/v1/catalogos/columnas/34/",
            {"nombre_homologado": "Cambio no autorizado"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            ColumnaTributaria.objects.get(pk=34).nombre_homologado,
            "Crédito por impuesto tasa adicional, Ex. Art. 21 LIR",
        )

    def test_tipo_invalido_se_rechaza_y_no_actualiza_el_catalogo(self):
        columna = ColumnaTributaria.objects.get(pk=34)
        response = self.cliente(self.admin).patch(
            f"/api/v1/catalogos/columnas/{columna.pk}/",
            {"tipo_dato": "SCRIPT"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        columna.refresh_from_db()
        self.assertEqual(columna.tipo_dato, ColumnaTributaria.TipoDato.MONTO)

    def test_semilla_idempotente_preserva_ediciones_del_catalogo(self):
        ColumnaTributaria.objects.filter(pk=34).update(
            nombre_homologado="Nombre ajustado",
            formula="Fórmula ajustada por docente",
        )

        call_command("sembrar_catalogos", verbosity=0)

        columna = ColumnaTributaria.objects.get(pk=34)
        self.assertEqual(columna.nombre_homologado, "Nombre ajustado")
        self.assertEqual(columna.formula, "Fórmula ajustada por docente")
