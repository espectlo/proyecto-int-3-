from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.cuentas.models import Corredor, Rol, Usuario
from apps.calificaciones.models import (
    Calificacion,
    Instrumento,
    LogAuditoria,
    Mercado,
    OrigenInformacion,
)


class CalificacionesApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_corredor = Rol.objects.create(
            codigo=Rol.Codigo.CORREDOR,
            nombre="Corredor",
        )
        cls.rol_operador = Rol.objects.create(
            codigo=Rol.Codigo.OPERADOR_BOLSA,
            nombre="Operador de Bolsa",
        )
        cls.rol_auditor = Rol.objects.create(
            codigo=Rol.Codigo.AUDITOR,
            nombre="Auditor",
        )
        cls.rol_administrador = Rol.objects.create(
            codigo=Rol.Codigo.ADMINISTRADOR,
            nombre="Administrador",
        )
        cls.corredor_a = Corredor.objects.create(
            rut="76.222.222-2",
            nombre="Corredora A",
        )
        cls.corredor_b = Corredor.objects.create(
            rut="76.333.333-3",
            nombre="Corredora B",
        )
        cls.mercado = Mercado.objects.create(codigo="ACN", nombre="Acciones")
        cls.instrumento = Instrumento.objects.create(
            mercado=cls.mercado,
            codigo="COPEC",
            nombre="Copec",
        )
        cls.origen_manual = OrigenInformacion.objects.create(
            codigo=OrigenInformacion.Codigo.INGRESO_MANUAL,
            descripcion="Ingreso manual",
        )
        cls.origen_sistema = OrigenInformacion.objects.create(
            codigo=OrigenInformacion.Codigo.SISTEMA,
            descripcion="Sistema",
        )
        cls.usuario_corredor_a = cls.crear_usuario(
            "corredor-a@example.test",
            cls.rol_corredor,
            cls.corredor_a,
        )
        cls.usuario_corredor_b = cls.crear_usuario(
            "corredor-b@example.test",
            cls.rol_corredor,
            cls.corredor_b,
        )
        cls.usuario_operador = cls.crear_usuario(
            "operador@example.test",
            cls.rol_operador,
        )
        cls.usuario_auditor = cls.crear_usuario(
            "auditor@example.test",
            cls.rol_auditor,
        )
        cls.usuario_administrador = cls.crear_usuario(
            "administrador@example.test",
            cls.rol_administrador,
        )
        cls.calificacion_corredor_a = cls.crear_calificacion(
            cls.usuario_corredor_a,
            cls.corredor_a,
            secuencia=10001,
        )
        cls.calificacion_corredor_b = cls.crear_calificacion(
            cls.usuario_corredor_b,
            cls.corredor_b,
            secuencia=10002,
        )
        cls.calificacion_bolsa = cls.crear_calificacion(
            cls.usuario_operador,
            None,
            secuencia=10003,
        )

    @classmethod
    def crear_usuario(cls, email, rol, corredor=None):
        cuenta = get_user_model().objects.create_user(
            username=email,
            email=email,
            password="Clave-segura-123!",
        )
        return Usuario.objects.create(
            cuenta=cuenta,
            email=email,
            rol=rol,
            corredor=corredor,
        )

    @classmethod
    def crear_calificacion(cls, usuario, corredor, secuencia):
        return Calificacion.objects.create(
            corredor=corredor,
            instrumento=cls.instrumento,
            origen=cls.origen_sistema,
            usuario=usuario,
            ejercicio=2025,
            secuencia_evento=secuencia,
            fecha_pago=date(2025, 5, 12),
        )

    def cliente_para(self, perfil):
        client = APIClient()
        client.force_authenticate(user=perfil.cuenta)
        return client

    def test_corredor_solo_ve_registros_propios_y_de_bolsa(self):
        response = self.cliente_para(self.usuario_corredor_a).get(
            "/api/v1/calificaciones/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {registro["id"] for registro in response.data}
        self.assertEqual(
            ids,
            {self.calificacion_corredor_a.pk, self.calificacion_bolsa.pk},
        )

    def test_operador_solo_ve_registros_de_bolsa(self):
        response = self.cliente_para(self.usuario_operador).get(
            "/api/v1/calificaciones/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [registro["id"] for registro in response.data],
            [self.calificacion_bolsa.pk],
        )

    def test_auditor_ve_registros_y_audita_consulta_por_corredor(self):
        response = self.cliente_para(self.usuario_auditor).get(
            "/api/v1/calificaciones/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.usuario_auditor,
                corredor=self.corredor_a,
                accion=LogAuditoria.Accion.CONSULTA_AUDITOR,
            ).exists()
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.usuario_auditor,
                corredor=self.corredor_b,
                accion=LogAuditoria.Accion.CONSULTA_AUDITOR,
            ).exists()
        )

    def test_corredor_no_puede_leer_otro_corredor_y_genera_log(self):
        response = self.cliente_para(self.usuario_corredor_a).get(
            f"/api/v1/calificaciones/{self.calificacion_corredor_b.pk}/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.usuario_corredor_a,
                accion=LogAuditoria.Accion.ACCESO_DENEGADO,
            ).exists()
        )

    def test_corredor_crea_calificacion_local_sin_poder_forzar_origen(self):
        response = self.cliente_para(self.usuario_corredor_a).post(
            "/api/v1/calificaciones/",
            {
                "instrumento": self.instrumento.pk,
                "ejercicio": 2025,
                "secuencia_evento": 10004,
                "fecha_pago": "2025-09-10",
                "descripcion_dividendo": "Dividendo de prueba",
                "origen": self.origen_sistema.pk,
                "corredor": self.corredor_b.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        nueva = Calificacion.objects.get(pk=response.data["id"])
        self.assertEqual(nueva.corredor, self.corredor_a)
        self.assertEqual(nueva.origen, self.origen_manual)
        self.assertEqual(nueva.usuario, self.usuario_corredor_a)
        self.assertEqual(response.data["version"], 1)
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.usuario_corredor_a,
                id_registro=nueva.pk,
                accion=LogAuditoria.Accion.INGRESO,
            ).exists()
        )

    def test_corredor_no_puede_escribir_calificacion_de_bolsa(self):
        response = self.cliente_para(self.usuario_corredor_a).patch(
            f"/api/v1/calificaciones/{self.calificacion_bolsa.pk}/",
            {"version": 1, "descripcion_dividendo": "No autorizado"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.calificacion_bolsa.refresh_from_db()
        self.assertEqual(self.calificacion_bolsa.descripcion_dividendo, "")

    def test_actualizacion_exige_version_y_incrementa_version(self):
        client = self.cliente_para(self.usuario_corredor_a)
        url = f"/api/v1/calificaciones/{self.calificacion_corredor_a.pk}/"

        sin_version = client.patch(
            url,
            {"descripcion_dividendo": "Actualización"},
            format="json",
        )
        self.assertEqual(sin_version.status_code, status.HTTP_400_BAD_REQUEST)

        actualizado = client.patch(
            url,
            {"version": 1, "descripcion_dividendo": "Actualización"},
            format="json",
        )
        self.assertEqual(actualizado.status_code, status.HTTP_200_OK)
        self.assertEqual(actualizado.data["version"], 2)

    def test_modificacion_actualiza_datos_del_evento_y_audita_cambios(self):
        response = self.cliente_para(self.usuario_corredor_a).patch(
            f"/api/v1/calificaciones/{self.calificacion_corredor_a.pk}/",
            {
                "version": 1,
                "ejercicio": 2024,
                "secuencia_evento": 10011,
                "numero_dividendo": 2,
                "fecha_pago": "2024-06-15",
                "descripcion_dividendo": "Dividendo corregido",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], 2)
        self.calificacion_corredor_a.refresh_from_db()
        self.assertEqual(self.calificacion_corredor_a.ejercicio, 2024)
        self.assertEqual(self.calificacion_corredor_a.secuencia_evento, 10011)
        self.assertEqual(self.calificacion_corredor_a.numero_dividendo, 2)
        self.assertEqual(
            self.calificacion_corredor_a.descripcion_dividendo,
            "Dividendo corregido",
        )
        log = LogAuditoria.objects.get(
            usuario=self.usuario_corredor_a,
            id_registro=self.calificacion_corredor_a.pk,
            accion=LogAuditoria.Accion.MODIFICACION,
        )
        self.assertEqual(log.valor_anterior["version"], 1)
        self.assertEqual(log.valor_nuevo["version"], 2)

    def test_version_obsoleta_conflicta_y_no_sobrescribe(self):
        client = self.cliente_para(self.usuario_corredor_a)
        url = f"/api/v1/calificaciones/{self.calificacion_corredor_a.pk}/"
        primero = client.patch(
            url,
            {"version": 1, "descripcion_dividendo": "Cambio más reciente"},
            format="json",
        )
        segundo = client.patch(
            url,
            {"version": 1, "descripcion_dividendo": "Cambio obsoleto"},
            format="json",
        )

        self.assertEqual(primero.status_code, status.HTTP_200_OK)
        self.assertEqual(segundo.status_code, status.HTTP_409_CONFLICT)
        self.calificacion_corredor_a.refresh_from_db()
        self.assertEqual(
            self.calificacion_corredor_a.descripcion_dividendo,
            "Cambio más reciente",
        )

    def test_eliminacion_es_logica_y_auditada(self):
        response = self.cliente_para(self.usuario_corredor_a).delete(
            f"/api/v1/calificaciones/{self.calificacion_corredor_a.pk}/",
            {"version": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.calificacion_corredor_a.refresh_from_db()
        self.assertEqual(
            self.calificacion_corredor_a.estado,
            Calificacion.Estado.ELIMINADA,
        )
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.usuario_corredor_a,
                id_registro=self.calificacion_corredor_a.pk,
                accion=LogAuditoria.Accion.ELIMINACION,
            ).exists()
        )
        listado = self.cliente_para(self.usuario_corredor_a).get(
            "/api/v1/calificaciones/"
        )
        self.assertNotIn(
            self.calificacion_corredor_a.pk,
            {registro["id"] for registro in listado.data},
        )

    def test_auditor_no_puede_modificar(self):
        response = self.cliente_para(self.usuario_auditor).patch(
            f"/api/v1/calificaciones/{self.calificacion_corredor_a.pk}/",
            {"version": 1, "descripcion_dividendo": "Intento"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_sin_perfil_no_accede_a_calificaciones(self):
        cuenta = get_user_model().objects.create_user(
            username="sin-perfil",
            email="sin-perfil@example.test",
            password="Clave-segura-123!",
        )
        client = APIClient()
        client.force_authenticate(user=cuenta)

        response = client.get("/api/v1/calificaciones/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_catalogos_requieren_perfil_activo(self):
        response = self.cliente_para(self.usuario_corredor_a).get(
            "/api/v1/catalogos/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mercados"][0]["codigo"], "ACN")
        self.assertEqual(response.data["instrumentos"][0]["codigo"], "COPEC")

    def test_auditoria_paginada_es_accesible_auditor_y_administrador(self):
        LogAuditoria.objects.create(
            usuario=self.usuario_corredor_a,
            corredor=self.corredor_a,
            entidad="Calificacion",
            id_registro=self.calificacion_corredor_a.pk,
            accion=LogAuditoria.Accion.INGRESO,
            valor_nuevo={"ejercicio": 2025},
        )

        auditoria = self.cliente_para(self.usuario_auditor).get(
            "/api/v1/auditoria/?accion=INGRESO&limite=1"
        )
        administrador = self.cliente_para(self.usuario_administrador).get(
            "/api/v1/auditoria/"
        )

        self.assertEqual(auditoria.status_code, status.HTTP_200_OK)
        self.assertEqual(auditoria.data["total"], 1)
        self.assertEqual(
            auditoria.data["resultados"][0]["usuario"],
            self.usuario_corredor_a.email,
        )
        self.assertEqual(administrador.status_code, status.HTTP_200_OK)

    def test_auditoria_rechaza_roles_sin_permiso_y_limites_invalidos(self):
        denegado = self.cliente_para(self.usuario_corredor_a).get(
            "/api/v1/auditoria/"
        )
        limite_invalido = self.cliente_para(self.usuario_auditor).get(
            "/api/v1/auditoria/?limite=101"
        )

        self.assertEqual(denegado.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(limite_invalido.status_code, status.HTTP_400_BAD_REQUEST)
