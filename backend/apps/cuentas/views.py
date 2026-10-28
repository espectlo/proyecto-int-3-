from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from apps.calificaciones.models import LogAuditoria

from .backends import EmailProfileBackend, _PASSWORD_DUMMY
from .models import Usuario
from .permissions import PerfilActivoPermission


MENSAJE_CREDENCIALES_INVALIDAS = "No fue posible iniciar sesión con esos datos."


def _agregar_perfil_al_token(token, perfil):
    token["rol"] = perfil.rol.codigo
    token["corredor_id"] = perfil.corredor_id
    return token


def _emitir_tokens(perfil):
    refresh = _agregar_perfil_al_token(
        RefreshToken.for_user(perfil.cuenta),
        perfil,
    )
    return str(refresh.access_token), str(refresh)


def _establecer_cookie_refresh(response, token):
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        token,
        max_age=settings.JWT_REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.JWT_REFRESH_COOKIE_SECURE,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        path=settings.JWT_REFRESH_COOKIE_PATH,
    )


def _eliminar_cookie_refresh(response):
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )


def _registrar_intento_rechazado(perfil):
    LogAuditoria.objects.create(
        usuario=perfil,
        corredor=perfil.corredor,
        entidad="Autenticacion",
        id_registro=perfil.pk,
        accion=LogAuditoria.Accion.ACCESO_DENEGADO,
        metodo="LOGIN_RECHAZADO",
    )


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class TokenLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    @method_decorator(csrf_protect)
    def post(self, request):
        if not isinstance(request.data, dict):
            return Response(
                {"detalle": "El cuerpo de la solicitud debe ser un objeto JSON."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = request.data.get("email")
        password = request.data.get("password")
        if (
            not isinstance(email, str)
            or not isinstance(password, str)
            or not email.strip()
            or not password
        ):
            return Response(
                {"detalle": "Correo electrónico y contraseña son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = email.strip().lower()
        ahora = timezone.now()

        with transaction.atomic():
            perfil = (
                Usuario.objects.select_for_update(of=("self",))
                .select_related("cuenta", "rol", "corredor")
                .filter(email__iexact=email)
                .first()
            )

            if perfil is None:
                check_password(password, _PASSWORD_DUMMY)
                valido = False
            else:
                bloqueado = (
                    perfil.bloqueado_hasta is not None
                    and perfil.bloqueado_hasta > ahora
                )
                valido = not bloqueado and authenticate(
                    request,
                    email=email,
                    password=password,
                ) is not None

                if (
                    not bloqueado
                    and not valido
                    and perfil.activo
                    and perfil.cuenta.is_active
                ):
                    perfil.intentos_fallidos = min(
                        perfil.intentos_fallidos + 1,
                        settings.LOGIN_MAX_ATTEMPTS,
                    )
                    if perfil.intentos_fallidos >= settings.LOGIN_MAX_ATTEMPTS:
                        perfil.bloqueado_hasta = ahora + timedelta(
                            minutes=settings.LOGIN_LOCK_MINUTES
                        )
                    perfil.save(
                        update_fields=[
                            "intentos_fallidos",
                            "bloqueado_hasta",
                            "actualizado_en",
                        ]
                    )
                    _registrar_intento_rechazado(perfil)

                if bloqueado:
                    valido = False

            if not valido or perfil is None:
                return Response(
                    {"detalle": MENSAJE_CREDENCIALES_INVALIDAS},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            if perfil.intentos_fallidos or perfil.bloqueado_hasta:
                perfil.intentos_fallidos = 0
                perfil.bloqueado_hasta = None
                perfil.save(
                    update_fields=[
                        "intentos_fallidos",
                        "bloqueado_hasta",
                        "actualizado_en",
                    ]
                )

            access, refresh = _emitir_tokens(perfil)

        response = Response(
            {
                "access": access,
                "usuario": {
                    "id": perfil.pk,
                    "email": perfil.email,
                    "nombre": perfil.cuenta.get_full_name() or perfil.email,
                    "rol": perfil.rol.codigo,
                    "corredor_id": perfil.corredor_id,
                    "debe_cambiar_clave": perfil.debe_cambiar_clave,
                },
            },
            status=status.HTTP_200_OK,
        )
        _establecer_cookie_refresh(response, refresh)
        return response


class CsrfTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        response = Response({"csrfToken": get_token(request)})
        response.set_cookie(
            settings.CSRF_COOKIE_NAME,
            get_token(request),
            httponly=settings.CSRF_COOKIE_HTTPONLY,
            secure=settings.CSRF_COOKIE_SECURE,
            samesite=settings.CSRF_COOKIE_SAMESITE,
        )
        return response


@method_decorator(csrf_protect, name="dispatch")
class TokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        raw_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not raw_refresh:
            return Response(
                {"detalle": "La sesión expiró. Inicia sesión nuevamente."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            refresh_anterior = RefreshToken(raw_refresh)
            cuenta_id = refresh_anterior[api_settings.USER_ID_CLAIM]
            perfil = Usuario.objects.select_related(
                "cuenta", "rol", "corredor"
            ).get(cuenta_id=cuenta_id)
            if not EmailProfileBackend._perfil_activo(perfil):
                raise TokenError("La cuenta ya no está habilitada.")

            refresh_anterior.blacklist()
            access, refresh_nuevo = _emitir_tokens(perfil)
        except (TokenError, Usuario.DoesNotExist, KeyError, TypeError):
            response = Response(
                {"detalle": "La sesión expiró. Inicia sesión nuevamente."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _eliminar_cookie_refresh(response)
            return response

        response = Response({"access": access}, status=status.HTTP_200_OK)
        _establecer_cookie_refresh(response, refresh_nuevo)
        return response


@method_decorator(csrf_protect, name="dispatch")
class TokenLogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        raw_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except TokenError:
                pass

        response = Response(status=status.HTTP_204_NO_CONTENT)
        _eliminar_cookie_refresh(response)
        return response


class PerfilActualView(APIView):
    permission_classes = [IsAuthenticated, PerfilActivoPermission]

    def get(self, request):
        perfil = request.nuam_profile
        return Response(
            {
                "id": perfil.pk,
                "email": perfil.email,
                "nombre": request.user.get_full_name() or perfil.email,
                "rol": perfil.rol.codigo,
                "corredor_id": perfil.corredor_id,
                "debe_cambiar_clave": perfil.debe_cambiar_clave,
            }
        )


class CambiarClaveView(APIView):
    permission_classes = [IsAuthenticated, PerfilActivoPermission]

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response(
                {"detalle": "El cuerpo de la solicitud debe ser un objeto JSON."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        clave_actual = request.data.get("clave_actual")
        clave_nueva = request.data.get("clave_nueva")
        confirmacion = request.data.get("confirmacion")
        if not all(
            isinstance(valor, str) and valor
            for valor in (clave_actual, clave_nueva, confirmacion)
        ):
            return Response(
                {"detalle": "Completa la contraseña actual y la nueva contraseña."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if clave_nueva != confirmacion:
            return Response(
                {
                    "confirmacion": (
                        "La confirmación no coincide con la nueva contraseña."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            perfil = (
                Usuario.objects.select_for_update(of=("self",))
                .select_related("cuenta", "rol", "corredor")
                .get(pk=request.nuam_profile.pk)
            )
            cuenta = perfil.cuenta
            if not cuenta.check_password(clave_actual):
                return Response(
                    {"clave_actual": "La contraseña actual no es correcta."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                password_validation.validate_password(clave_nueva, cuenta)
            except DjangoValidationError as error:
                return Response(
                    {"clave_nueva": list(error.messages)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cuenta.set_password(clave_nueva)
            cuenta.save(update_fields=["password"])
            perfil.debe_cambiar_clave = False
            perfil.save(update_fields=["debe_cambiar_clave", "actualizado_en"])
            tokens = OutstandingToken.objects.filter(user=cuenta)
            for token in tokens:
                BlacklistedToken.objects.get_or_create(token=token)
            LogAuditoria.objects.create(
                usuario=perfil,
                corredor=perfil.corredor,
                entidad="Usuario",
                id_registro=perfil.pk,
                accion=LogAuditoria.Accion.CAMBIO_CLAVE,
                metodo="CAMBIO_CLAVE",
            )
            access, refresh = _emitir_tokens(perfil)

        response = Response({"access": access}, status=status.HTTP_200_OK)
        _establecer_cookie_refresh(response, refresh)
        return response
