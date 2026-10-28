from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cuentas.models import Rol
from apps.cuentas.permissions import PerfilSinCambioClavePermission

from .models import Calificacion, LogAuditoria, OrigenInformacion
from .serializers import CalificacionSerializer


class ConflictoVersion(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "La calificación cambió desde que la consultaste. Recarga el registro "
        "antes de guardar tus cambios."
    )
    default_code = "conflicto_de_version"


class CalificacionViewSet(viewsets.ModelViewSet):
    serializer_class = CalificacionSerializer
    permission_classes = [IsAuthenticated, PerfilSinCambioClavePermission]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def _perfil(self):
        if not hasattr(self.request, "nuam_profile"):
            self.check_permissions(self.request)
        return self.request.nuam_profile

    def _puede_ver(self, perfil, calificacion):
        if perfil.rol.codigo == Rol.Codigo.AUDITOR:
            return True
        if perfil.rol.codigo == Rol.Codigo.CORREDOR:
            return calificacion.corredor_id in (None, perfil.corredor_id)
        if perfil.rol.codigo == Rol.Codigo.OPERADOR_BOLSA:
            return calificacion.corredor_id is None
        return False

    def _puede_modificar(self, perfil, calificacion):
        if perfil.rol.codigo == Rol.Codigo.CORREDOR:
            return calificacion.corredor_id == perfil.corredor_id
        if perfil.rol.codigo == Rol.Codigo.OPERADOR_BOLSA:
            return calificacion.corredor_id is None
        return False

    def get_queryset(self):
        perfil = self._perfil()
        queryset = (
            Calificacion.objects.filter(estado=Calificacion.Estado.VIGENTE)
            .select_related(
                "instrumento__mercado",
                "origen",
                "corredor",
                "usuario",
            )
            .prefetch_related("montos", "factores")
        )

        if perfil.rol.codigo == Rol.Codigo.CORREDOR:
            queryset = queryset.filter(
                Q(corredor=perfil.corredor) | Q(corredor__isnull=True)
            )
        elif perfil.rol.codigo == Rol.Codigo.OPERADOR_BOLSA:
            queryset = queryset.filter(corredor__isnull=True)
        elif perfil.rol.codigo != Rol.Codigo.AUDITOR:
            return queryset.none()

        parametros = self.request.query_params
        if parametros.get("mercado"):
            queryset = queryset.filter(
                instrumento__mercado__codigo=parametros["mercado"]
            )
        if parametros.get("origen"):
            queryset = queryset.filter(origen__codigo=parametros["origen"])
        if parametros.get("ejercicio"):
            if not parametros["ejercicio"].isdecimal():
                return queryset.none()
            queryset = queryset.filter(ejercicio=int(parametros["ejercicio"]))
        if parametros.get("q"):
            texto = parametros["q"].strip()[:100]
            queryset = queryset.filter(
                Q(instrumento__codigo__icontains=texto)
                | Q(instrumento__nombre__icontains=texto)
                | Q(descripcion_dividendo__icontains=texto)
            )
        return queryset

    def get_object(self):
        try:
            calificacion = (
                Calificacion.objects.select_related(
                    "instrumento__mercado",
                    "origen",
                    "corredor",
                    "usuario",
                )
                .prefetch_related("montos", "factores")
                .get(pk=self.kwargs["pk"])
            )
        except Calificacion.DoesNotExist as error:
            from django.http import Http404

            raise Http404 from error

        perfil = self._perfil()
        if (
            calificacion.estado != Calificacion.Estado.VIGENTE
            or not self._puede_ver(perfil, calificacion)
        ):
            self._registrar_denegacion(perfil, calificacion)
            raise PermissionDenied("No tienes acceso a esta calificación.")
        return calificacion

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        perfil = self._perfil()
        if perfil.rol.codigo == Rol.Codigo.AUDITOR:
            corredor_ids = (
                Calificacion.objects.filter(
                    pk__in=self.filter_queryset(self.get_queryset()).values("pk"),
                    corredor__isnull=False,
                )
                .values_list("corredor_id", flat=True)
                .distinct()
            )
            for corredor_id in corredor_ids:
                self._registrar_consulta_auditor(perfil, corredor_id)
        return response

    def retrieve(self, request, *args, **kwargs):
        calificacion = self.get_object()
        perfil = self._perfil()
        if perfil.rol.codigo == Rol.Codigo.AUDITOR and calificacion.corredor_id:
            self._registrar_consulta_auditor(perfil, calificacion.corredor_id)
        serializer = self.get_serializer(calificacion)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        perfil = self._perfil()
        if perfil.rol.codigo not in (
            Rol.Codigo.CORREDOR,
            Rol.Codigo.OPERADOR_BOLSA,
        ):
            self._registrar_denegacion(perfil)
            raise PermissionDenied("Tu rol no puede crear calificaciones.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        origen = OrigenInformacion.objects.get(
            codigo=OrigenInformacion.Codigo.INGRESO_MANUAL
        )
        corredor = (
            perfil.corredor
            if perfil.rol.codigo == Rol.Codigo.CORREDOR
            else None
        )
        try:
            with transaction.atomic():
                calificacion = serializer.save(
                    usuario=perfil,
                    corredor=corredor,
                    origen=origen,
                    metodo_actualizacion=(
                        Calificacion.MetodoActualizacion.INGRESO_MANUAL
                    ),
                )
                self._registrar_auditoria(
                    perfil,
                    calificacion,
                    LogAuditoria.Accion.INGRESO,
                    valor_nuevo=self.get_serializer(calificacion).data,
                )
        except IntegrityError:
            return Response(
                {
                    "detalle": (
                        "Ya existe una calificación vigente con los mismos datos "
                        "de identificación."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            self.get_serializer(calificacion).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        perfil = self._perfil()
        calificacion = self.get_object()
        if not self._puede_modificar(perfil, calificacion):
            self._registrar_denegacion(perfil, calificacion)
            raise PermissionDenied("No puedes modificar esta calificación.")
        if "version" not in request.data:
            return Response(
                {"version": "Este campo es obligatorio para evitar sobrescrituras."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            version_solicitada = int(request.data["version"])
        except (TypeError, ValueError):
            return Response(
                {"version": "Debe ser un número entero válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if version_solicitada != calificacion.version:
            raise ConflictoVersion()

        serializer = self.get_serializer(
            calificacion,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        anterior = self.get_serializer(calificacion).data
        try:
            with transaction.atomic():
                calificacion = Calificacion.objects.select_for_update().get(
                    pk=calificacion.pk
                )
                if calificacion.version != version_solicitada:
                    raise ConflictoVersion()
                anterior = self.get_serializer(calificacion).data
                serializer.instance = calificacion
                actualizada = serializer.save(
                    metodo_actualizacion=(
                        Calificacion.MetodoActualizacion.INGRESO_MANUAL
                    )
                )
                actualizada.version += 1
                actualizada.save()
                self._registrar_auditoria(
                    perfil,
                    actualizada,
                    LogAuditoria.Accion.MODIFICACION,
                    valor_anterior=anterior,
                    valor_nuevo=self.get_serializer(actualizada).data,
                )
        except IntegrityError:
            return Response(
                {"detalle": "Los cambios entran en conflicto con otra calificación."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(actualizada).data)

    def destroy(self, request, *args, **kwargs):
        perfil = self._perfil()
        calificacion = self.get_object()
        if not self._puede_modificar(perfil, calificacion):
            self._registrar_denegacion(perfil, calificacion)
            raise PermissionDenied("No puedes eliminar esta calificación.")
        if "version" not in request.data:
            return Response(
                {"version": "Este campo es obligatorio para evitar sobrescrituras."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            version_solicitada = int(request.data["version"])
        except (TypeError, ValueError):
            return Response(
                {"version": "Debe ser un número entero válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if version_solicitada != calificacion.version:
            raise ConflictoVersion()

        with transaction.atomic():
            calificacion = Calificacion.objects.select_for_update().get(
                pk=calificacion.pk
            )
            if calificacion.version != version_solicitada:
                raise ConflictoVersion()
            anterior = self.get_serializer(calificacion).data
            calificacion.estado = Calificacion.Estado.ELIMINADA
            calificacion.eliminada_en = timezone.now()
            calificacion.version += 1
            calificacion.save(
                update_fields=[
                    "estado",
                    "eliminada_en",
                    "version",
                    "fecha_ultima_modificacion",
                ]
            )
            self._registrar_auditoria(
                perfil,
                calificacion,
                LogAuditoria.Accion.ELIMINACION,
                valor_anterior=anterior,
                valor_nuevo=self.get_serializer(calificacion).data,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _registrar_denegacion(self, perfil, calificacion=None):
        LogAuditoria.objects.create(
            usuario=perfil,
            corredor=calificacion.corredor if calificacion else perfil.corredor,
            entidad="Calificacion",
            id_registro=calificacion.pk if calificacion else 0,
            accion=LogAuditoria.Accion.ACCESO_DENEGADO,
            metodo=self.request.method,
        )

    def _registrar_consulta_auditor(self, perfil, corredor_id):
        LogAuditoria.objects.create(
            usuario=perfil,
            corredor_id=corredor_id,
            entidad="Calificacion",
            id_registro=0,
            accion=LogAuditoria.Accion.CONSULTA_AUDITOR,
            metodo=self.request.method,
        )

    def _registrar_auditoria(
        self,
        perfil,
        calificacion,
        accion,
        valor_anterior=None,
        valor_nuevo=None,
    ):
        LogAuditoria.objects.create(
            usuario=perfil,
            corredor=calificacion.corredor,
            entidad="Calificacion",
            id_registro=calificacion.pk,
            accion=accion,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
            metodo=calificacion.metodo_actualizacion,
        )
