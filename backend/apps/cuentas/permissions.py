from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import BasePermission

from apps.calificaciones.models import LogAuditoria

from .backends import EmailProfileBackend
from .models import Rol, Usuario


class PerfilActivoPermission(BasePermission):
    message = "La cuenta no tiene un perfil NUAM activo."

    def has_permission(self, request, view):
        try:
            perfil = Usuario.objects.select_related(
                "cuenta", "rol", "corredor"
            ).get(cuenta_id=request.user.pk)
        except (AttributeError, ObjectDoesNotExist, Usuario.DoesNotExist):
            return False

        request.nuam_profile = perfil
        if not EmailProfileBackend._perfil_activo(perfil):
            _registrar_acceso_denegado(perfil, request)
            return False
        return True


class RolesPermitidosPermission(PerfilActivoPermission):
    message = "Tu rol no tiene permiso para realizar esta operación."
    roles_permitidos = ()

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        perfil = request.nuam_profile
        if perfil.debe_cambiar_clave:
            self.message = "Debes cambiar tu contraseña antes de continuar."
            _registrar_acceso_denegado(perfil, request)
            return False
        if perfil.rol.codigo not in self.roles_permitidos:
            _registrar_acceso_denegado(perfil, request)
            return False
        return True


class PerfilSinCambioClavePermission(PerfilActivoPermission):
    message = "Debes cambiar tu contraseña antes de continuar."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        perfil = request.nuam_profile
        if perfil.debe_cambiar_clave:
            _registrar_acceso_denegado(perfil, request)
            return False
        return True


def _registrar_acceso_denegado(perfil, request):
    LogAuditoria.objects.create(
        usuario=perfil,
        corredor=perfil.corredor,
        entidad="Autorizacion",
        id_registro=perfil.pk,
        accion=LogAuditoria.Accion.ACCESO_DENEGADO,
        metodo=request.method[:30],
    )


class SoloAdministradorPermission(RolesPermitidosPermission):
    roles_permitidos = (Rol.Codigo.ADMINISTRADOR,)


class SoloAuditoriaPermission(RolesPermitidosPermission):
    roles_permitidos = (
        Rol.Codigo.ADMINISTRADOR,
        Rol.Codigo.AUDITOR,
    )


class CargaMasivaPermission(RolesPermitidosPermission):
    roles_permitidos = (
        Rol.Codigo.CORREDOR,
        Rol.Codigo.OPERADOR_BOLSA,
    )
