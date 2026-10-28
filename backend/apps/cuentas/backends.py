from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .models import Usuario


_PASSWORD_DUMMY = make_password("credencial-invalida-para-verificacion")


class EmailProfileBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        identificador = (email or username or "").strip().lower()
        if not identificador or password is None:
            return None

        try:
            perfil = Usuario.objects.select_related(
                "cuenta", "rol", "corredor"
            ).get(email__iexact=identificador)
        except Usuario.DoesNotExist:
            check_password(password, _PASSWORD_DUMMY)
            return None

        cuenta = perfil.cuenta
        if not cuenta.check_password(password):
            return None
        if not self._perfil_activo(perfil):
            return None
        return cuenta

    def get_user(self, user_id):
        user_model = get_user_model()
        try:
            return user_model._default_manager.get(pk=user_id)
        except user_model.DoesNotExist:
            return None

    @staticmethod
    def _perfil_activo(perfil):
        return (
            perfil.activo
            and perfil.cuenta.is_active
            and (perfil.corredor is None or perfil.corredor.activo)
            and (
                perfil.bloqueado_hasta is None
                or perfil.bloqueado_hasta <= timezone.now()
            )
        )
