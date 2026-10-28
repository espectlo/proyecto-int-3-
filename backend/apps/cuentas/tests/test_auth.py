from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from apps.calificaciones.models import LogAuditoria
from apps.cuentas.models import Corredor, Rol, Usuario
from apps.cuentas.permissions import SoloAdministradorPermission


@override_settings(
    LOGIN_RATE_LIMIT="30/min",
    JWT_REFRESH_COOKIE_SECURE=False,
)
class AutenticacionApiTests(TestCase):
    password = "Clave-segura-123!"

    @classmethod
    def setUpTestData(cls):
        cls.rol_corredor = Rol.objects.create(
            codigo=Rol.Codigo.CORREDOR,
            nombre="Corredor",
        )
        cls.rol_admin = Rol.objects.create(
            codigo=Rol.Codigo.ADMINISTRADOR,
            nombre="Administrador",
        )
        cls.corredor = Corredor.objects.create(
            rut="76.111.111-1",
            nombre="Corredora de prueba",
        )
        cls.cuenta = get_user_model().objects.create_user(
            username="usuario-prueba",
            email="cuenta@example.test",
            password=cls.password,
            first_name="Usuario",
            last_name="Prueba",
        )
        cls.perfil = Usuario.objects.create(
            cuenta=cls.cuenta,
            email="usuario@example.test",
            rol=cls.rol_corredor,
            corredor=cls.corredor,
        )

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def csrf_token(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["csrfToken"]

    def post_login(self, email="usuario@example.test", password=None):
        csrf = self.csrf_token()
        return self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": password or self.password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

    def test_login_emite_access_y_refresh_http_only(self):
        response = self.post_login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["usuario"]["rol"], "CORREDOR")
        self.assertEqual(response.data["usuario"]["corredor_id"], self.corredor.pk)
        refresh_cookie = response.cookies["nuam_refresh"]
        self.assertTrue(refresh_cookie["httponly"])
        self.assertEqual(refresh_cookie["samesite"], "Strict")
        claims = AccessToken(response.data["access"])
        self.assertEqual(claims["rol"], "CORREDOR")
        self.assertEqual(claims["corredor_id"], self.corredor.pk)

    def test_access_token_autoriza_perfil_actual(self):
        login = self.post_login()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.data['access']}"
        )

        response = self.client.get("/api/v1/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "usuario@example.test")
        self.assertEqual(response.data["rol"], "CORREDOR")
        self.assertEqual(response.data["corredor_id"], self.corredor.pk)

    def test_login_rechaza_json_con_campos_ausentes(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            {"email": "usuario@example.test"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_exige_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            "/api/v1/auth/login/",
            {"email": "usuario@example.test", "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cinco_intentos_fallidos_bloquean_por_quince_minutos(self):
        for _ in range(5):
            response = self.post_login(password="incorrecta")
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.intentos_fallidos, 5)
        self.assertGreater(
            self.perfil.bloqueado_hasta,
            timezone.now() + timedelta(minutes=14),
        )
        self.assertEqual(
            LogAuditoria.objects.filter(
                usuario=self.perfil,
                accion=LogAuditoria.Accion.ACCESO_DENEGADO,
            ).count(),
            5,
        )

    def test_intento_durante_bloqueo_no_extiende_el_bloqueo(self):
        self.perfil.intentos_fallidos = 5
        self.perfil.bloqueado_hasta = timezone.now() + timedelta(minutes=10)
        self.perfil.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
        bloqueo_original = self.perfil.bloqueado_hasta

        response = self.post_login()

        self.perfil.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.perfil.bloqueado_hasta, bloqueo_original)

    def test_login_correcto_reinicia_contador_y_bloqueo_expirado(self):
        self.perfil.intentos_fallidos = 4
        self.perfil.bloqueado_hasta = timezone.now() - timedelta(seconds=1)
        self.perfil.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

        response = self.post_login()

        self.perfil.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.perfil.intentos_fallidos, 0)
        self.assertIsNone(self.perfil.bloqueado_hasta)

    def test_refresh_rota_token_y_exige_csrf(self):
        login = self.post_login()
        refresh = login.cookies["nuam_refresh"].value
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        client.cookies["nuam_refresh"] = refresh

        sin_csrf = client.post(
            "/api/v1/auth/refresh/",
            {},
            format="json",
        )
        self.assertEqual(sin_csrf.status_code, status.HTTP_403_FORBIDDEN)

        with_csrf = client.post(
            "/api/v1/auth/refresh/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(with_csrf.status_code, status.HTTP_200_OK)
        self.assertIn("access", with_csrf.data)
        self.assertNotEqual(
            with_csrf.cookies["nuam_refresh"].value,
            refresh,
        )

        client.cookies["nuam_refresh"] = refresh
        token_anterior = client.post(
            "/api/v1/auth/refresh/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(
            token_anterior.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_refresh_actualiza_reclamos_con_rol_vigente(self):
        login = self.post_login()
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        client.cookies["nuam_refresh"] = login.cookies["nuam_refresh"].value
        self.perfil.rol = self.rol_admin
        self.perfil.corredor = None
        self.perfil.save(update_fields=["rol", "corredor"])

        response = client.post(
            "/api/v1/auth/refresh/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            AccessToken(response.data["access"])["rol"],
            "ADMINISTRADOR",
        )

    def test_cierre_de_sesion_invalida_refresh(self):
        login = self.post_login()
        refresh = login.cookies["nuam_refresh"].value
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        client.cookies["nuam_refresh"] = refresh

        response = client.post(
            "/api/v1/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            client.post(
                "/api/v1/auth/refresh/",
                {},
                format="json",
                HTTP_X_CSRFTOKEN=csrf,
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_perfil_actual_rechaza_token_sin_perfil_activo(self):
        self.client.force_authenticate(user=self.cuenta)
        self.perfil.activo = False
        self.perfil.save(update_fields=["activo"])

        response = self.client.get("/api/v1/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_permiso_de_administrador_consulta_rol_vigente(self):
        factory = APIRequestFactory()
        request = factory.get("/api/v1/auth/usuarios/")
        request.user = self.cuenta
        permiso = SoloAdministradorPermission()
        view = APIView()

        self.assertFalse(permiso.has_permission(request, view))
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.perfil,
                entidad="Autorizacion",
                accion=LogAuditoria.Accion.ACCESO_DENEGADO,
            ).exists()
        )

        self.perfil.rol = self.rol_admin
        self.perfil.corredor = None
        self.perfil.save(update_fields=["rol", "corredor"])
        request = factory.get("/api/v1/auth/usuarios/")
        request.user = self.cuenta
        self.assertTrue(permiso.has_permission(request, view))


class CrearAdministradorInicialTests(TestCase):
    def test_crea_perfil_sin_exponer_ni_reutilizar_contrasena(self):
        rol = Rol.objects.create(
            codigo=Rol.Codigo.ADMINISTRADOR,
            nombre="Administrador",
        )
        salida = StringIO()
        with patch(
            "apps.cuentas.management.commands.crear_admin_inicial.getpass",
            side_effect=[
                "Una-frase-de-acceso-segura-2040",
                "Una-frase-de-acceso-segura-2040",
            ],
        ):
            call_command(
                "crear_admin_inicial",
                email="Admin@example.test",
                stdout=salida,
            )

        perfil = Usuario.objects.get(email="admin@example.test")
        self.assertEqual(perfil.rol, rol)
        self.assertTrue(
            perfil.cuenta.check_password("Una-frase-de-acceso-segura-2040")
        )
        self.assertNotIn("Una-frase-de-acceso-segura-2040", salida.getvalue())

    def test_no_crea_dos_perfiles_para_el_mismo_correo(self):
        rol = Rol.objects.create(
            codigo=Rol.Codigo.ADMINISTRADOR,
            nombre="Administrador",
        )
        cuenta = get_user_model().objects.create_user(
            username="admin@example.test",
            email="admin@example.test",
            password="Una-frase-de-acceso-segura-2040",
        )
        Usuario.objects.create(
            cuenta=cuenta,
            email="admin@example.test",
            rol=rol,
        )

        with self.assertRaisesMessage(CommandError, "Ya existe un perfil NUAM"):
            call_command("crear_admin_inicial", email="ADMIN@example.test")
