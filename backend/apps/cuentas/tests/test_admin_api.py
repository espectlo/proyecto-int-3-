from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.calificaciones.models import LogAuditoria
from apps.cuentas.models import Corredor, Rol, Usuario


class AdministracionUsuariosApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(
            codigo=Rol.Codigo.ADMINISTRADOR,
            nombre="Administrador",
        )
        cls.rol_corredor = Rol.objects.create(
            codigo=Rol.Codigo.CORREDOR,
            nombre="Corredor",
        )
        cls.rol_auditor = Rol.objects.create(
            codigo=Rol.Codigo.AUDITOR,
            nombre="Auditor",
        )
        cls.corredor = Corredor.objects.create(
            rut="76.444.444-4",
            nombre="Corredora para pruebas",
        )
        cls.admin = cls.crear_usuario(
            "admin@example.test",
            cls.rol_admin,
        )
        cls.no_admin = cls.crear_usuario(
            "auditor@example.test",
            cls.rol_auditor,
        )

    @classmethod
    def crear_usuario(cls, email, rol, corredor=None):
        cuenta = get_user_model().objects.create_user(
            username=email,
            email=email,
            password="Clave-de-prueba-2030!",
            first_name="Usuario",
        )
        return Usuario.objects.create(
            cuenta=cuenta,
            email=email,
            rol=rol,
            corredor=corredor,
        )

    @staticmethod
    def cliente(perfil):
        client = APIClient()
        client.force_authenticate(user=perfil.cuenta)
        return client

    def test_administrador_crea_usuario_con_clave_temporal_de_una_sola_vez(self):
        response = self.cliente(self.admin).post(
            "/api/v1/usuarios/",
            {
                "email": "Nuevo.Corredor@example.test",
                "nombre": "Nuevo Corredor",
                "rol": Rol.Codigo.CORREDOR,
                "corredor_id": self.corredor.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("clave_temporal", response.data)
        self.assertTrue(response.data["debe_cambiar_clave"])
        perfil = Usuario.objects.get(email="nuevo.corredor@example.test")
        self.assertTrue(perfil.cuenta.check_password(response.data["clave_temporal"]))
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.admin,
                id_registro=perfil.pk,
                accion=LogAuditoria.Accion.ADMIN_USUARIO,
                valor_nuevo__email=perfil.email,
            ).exists()
        )
        self.assertNotIn(
            response.data["clave_temporal"],
            str(
                LogAuditoria.objects.get(
                    usuario=self.admin,
                    id_registro=perfil.pk,
                ).valor_nuevo
            ),
        )

    def test_creacion_exige_corredor_y_no_permite_crear_admin(self):
        client = self.cliente(self.admin)
        sin_corredor = client.post(
            "/api/v1/usuarios/",
            {
                "email": "sin-corredor@example.test",
                "nombre": "Sin Corredor",
                "rol": Rol.Codigo.CORREDOR,
            },
            format="json",
        )
        admin_nuevo = client.post(
            "/api/v1/usuarios/",
            {
                "email": "otro-admin@example.test",
                "nombre": "Otro Administrador",
                "rol": Rol.Codigo.ADMINISTRADOR,
            },
            format="json",
        )

        self.assertEqual(sin_corredor.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(admin_nuevo.status_code, status.HTTP_400_BAD_REQUEST)

    def test_solo_administrador_accede_a_gestion_de_usuarios(self):
        response = self.cliente(self.no_admin).get("/api/v1/usuarios/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.no_admin,
                accion=LogAuditoria.Accion.ACCESO_DENEGADO,
            ).exists()
        )

    def test_desactivar_usuario_invalida_su_perfil_y_cuenta(self):
        objetivo = self.crear_usuario(
            "operador@example.test",
            Rol.objects.create(
                codigo=Rol.Codigo.OPERADOR_BOLSA,
                nombre="Operador",
            ),
        )

        response = self.cliente(self.admin).patch(
            f"/api/v1/usuarios/{objetivo.pk}/",
            {"activo": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        objetivo.refresh_from_db()
        objetivo.cuenta.refresh_from_db()
        self.assertFalse(objetivo.activo)
        self.assertFalse(objetivo.cuenta.is_active)
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.admin,
                id_registro=objetivo.pk,
                accion=LogAuditoria.Accion.ADMIN_USUARIO,
                metodo="DESACTIVAR",
            ).exists()
        )

    def test_administrador_no_puede_desactivarse_a_si_mismo(self):
        response = self.cliente(self.admin).patch(
            f"/api/v1/usuarios/{self.admin.pk}/",
            {"activo": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.activo)

    def test_restaurar_clave_invalida_la_anterior_y_exige_cambio(self):
        response = self.cliente(self.admin).post(
            f"/api/v1/usuarios/{self.no_admin.pk}/clave-temporal/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.no_admin.cuenta.refresh_from_db()
        self.assertTrue(
            self.no_admin.cuenta.check_password(response.data["clave_temporal"])
        )
        self.assertFalse(
            self.no_admin.cuenta.check_password("Clave-de-prueba-2030!")
        )
        self.no_admin.refresh_from_db()
        self.assertTrue(self.no_admin.debe_cambiar_clave)
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.admin,
                id_registro=self.no_admin.pk,
                metodo="RESTABLECER_CLAVE",
            ).exists()
        )

    def test_administrador_no_puede_restablecer_su_propia_clave(self):
        response = self.cliente(self.admin).post(
            f"/api/v1/usuarios/{self.admin.pk}/clave-temporal/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.debe_cambiar_clave)

    def test_clave_temporal_bloquea_api_hasta_cambio_obligatorio(self):
        creado = self.cliente(self.admin).post(
            "/api/v1/usuarios/",
            {
                "email": "temporal@example.test",
                "nombre": "Usuario Temporal",
                "rol": Rol.Codigo.CORREDOR,
                "corredor_id": self.corredor.pk,
            },
            format="json",
        )
        perfil = Usuario.objects.get(email="temporal@example.test")
        client = self.cliente(perfil)

        perfil_actual = client.get("/api/v1/auth/me/")
        catalogos_bloqueados = client.get("/api/v1/catalogos/")
        cambio = client.post(
            "/api/v1/auth/cambiar-clave/",
            {
                "clave_actual": creado.data["clave_temporal"],
                "clave_nueva": "Frase-nueva-segura-2034!",
                "confirmacion": "Frase-nueva-segura-2034!",
            },
            format="json",
        )

        self.assertEqual(perfil_actual.status_code, status.HTTP_200_OK)
        self.assertTrue(perfil_actual.data["debe_cambiar_clave"])
        self.assertEqual(catalogos_bloqueados.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(cambio.status_code, status.HTTP_200_OK)
        perfil.refresh_from_db()
        self.assertFalse(perfil.debe_cambiar_clave)
        self.assertTrue(perfil.cuenta.check_password("Frase-nueva-segura-2034!"))
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=perfil,
                accion=LogAuditoria.Accion.CAMBIO_CLAVE,
            ).exists()
        )
        self.assertEqual(
            client.get("/api/v1/catalogos/").status_code,
            status.HTTP_200_OK,
        )
