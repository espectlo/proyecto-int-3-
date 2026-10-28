import secrets

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from apps.calificaciones.models import LogAuditoria

from .models import Corredor, Rol, Usuario
from .permissions import SoloAdministradorPermission


ROLES_CREABLES = (
    Rol.Codigo.CORREDOR,
    Rol.Codigo.OPERADOR_BOLSA,
    Rol.Codigo.AUDITOR,
)


class CrearUsuarioSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=120)
    nombre = serializers.CharField(max_length=150)
    rol = serializers.ChoiceField(choices=ROLES_CREABLES)
    corredor_id = serializers.PrimaryKeyRelatedField(
        queryset=Corredor.objects.filter(activo=True),
        source="corredor",
        required=False,
        allow_null=True,
    )

    def validate_email(self, value):
        email = value.strip().lower()
        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD
        account_filter = Q(email__iexact=email)
        if username_field != "email":
            account_filter |= Q(**{f"{username_field}__iexact": email})
        if Usuario.objects.filter(email__iexact=email).exists() or (
            user_model.objects.filter(account_filter).exists()
        ):
            raise serializers.ValidationError(
                "Ya existe una cuenta con ese correo electrónico."
            )
        return email

    def validate(self, attrs):
        perfil_corredor = attrs.get("rol") == Rol.Codigo.CORREDOR
        if perfil_corredor and attrs.get("corredor") is None:
            raise serializers.ValidationError(
                {"corredor_id": "Asigna un corredor activo a este perfil."}
            )
        if not perfil_corredor and attrs.get("corredor") is not None:
            raise serializers.ValidationError(
                {"corredor_id": "Solo los usuarios corredor tienen un corredor."}
            )
        return attrs


class ActivarUsuarioSerializer(serializers.Serializer):
    activo = serializers.BooleanField()


class UsuariosAdminView(APIView):
    permission_classes = [IsAuthenticated, SoloAdministradorPermission]
    limite_maximo = 100

    def get(self, request):
        try:
            pagina = int(request.query_params.get("pagina", "1"))
            limite = int(request.query_params.get("limite", "25"))
        except ValueError:
            return Response(
                {"detalle": "La página y el límite deben ser números enteros."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pagina < 1 or not 1 <= limite <= self.limite_maximo:
            return Response(
                {
                    "detalle": (
                        "La página debe ser positiva y el límite estar entre 1 y 100."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = Usuario.objects.select_related("cuenta", "rol", "corredor")
        total = queryset.count()
        inicio = (pagina - 1) * limite
        return Response(
            {
                "total": total,
                "pagina": pagina,
                "limite": limite,
                "corredores": list(
                    Corredor.objects.filter(activo=True)
                    .values("id", "nombre", "rut")
                ),
                "resultados": [
                    self._representar(perfil)
                    for perfil in queryset[inicio:inicio + limite]
                ],
            }
        )

    def post(self, request):
        serializer = CrearUsuarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        email = datos["email"]
        temporary_password = secrets.token_urlsafe(24)
        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD

        try:
            with transaction.atomic():
                cuenta = user_model._default_manager.create_user(
                    **{username_field: email},
                    password=temporary_password,
                    email=email,
                    first_name=datos["nombre"],
                )
                perfil = Usuario.objects.create(
                    cuenta=cuenta,
                    email=email,
                    rol=Rol.objects.get(codigo=datos["rol"]),
                    corredor=datos.get("corredor"),
                    debe_cambiar_clave=True,
                )
                LogAuditoria.objects.create(
                    usuario=request.nuam_profile,
                    corredor=perfil.corredor,
                    entidad="Usuario",
                    id_registro=perfil.pk,
                    accion=LogAuditoria.Accion.ADMIN_USUARIO,
                    valor_nuevo={
                        "email": perfil.email,
                        "rol": perfil.rol.codigo,
                        "corredor": (
                            perfil.corredor.nombre if perfil.corredor_id else None
                        ),
                    },
                    metodo="CREAR",
                )
        except IntegrityError:
            return Response(
                {"detalle": "Ya existe una cuenta con ese correo electrónico."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                **self._representar(perfil),
                "clave_temporal": temporary_password,
            },
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _representar(perfil):
        return {
            "id": perfil.pk,
            "email": perfil.email,
            "nombre": perfil.cuenta.get_full_name() or perfil.email,
            "rol": perfil.rol.codigo,
            "corredor_id": perfil.corredor_id,
            "corredor": perfil.corredor.nombre if perfil.corredor_id else None,
            "activo": perfil.activo and perfil.cuenta.is_active,
            "debe_cambiar_clave": perfil.debe_cambiar_clave,
            "creado_en": perfil.creado_en,
        }


class UsuarioAdminDetalleView(APIView):
    permission_classes = [IsAuthenticated, SoloAdministradorPermission]

    def patch(self, request, pk):
        serializer = ActivarUsuarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        perfil = Usuario.objects.select_related(
            "cuenta", "rol", "corredor"
        ).filter(pk=pk).first()
        if perfil is None:
            return Response(
                {"detalle": "No se encontró el usuario."},
                status=status.HTTP_404_NOT_FOUND,
            )
        nuevo_estado = serializer.validated_data["activo"]
        actor = request.nuam_profile
        if perfil.pk == actor.pk and not nuevo_estado:
            return Response(
                {"activo": "No puedes desactivar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            perfil = (
                Usuario.objects.select_for_update(of=("self",))
                .select_related("cuenta", "rol", "corredor")
                .get(pk=perfil.pk)
            )
            if (
                not nuevo_estado
                and perfil.rol.codigo == Rol.Codigo.ADMINISTRADOR
                and perfil.activo
                and perfil.cuenta.is_active
            ):
                administradores_activos = list(
                    Usuario.objects.select_for_update(of=("self",))
                    .filter(
                        rol__codigo=Rol.Codigo.ADMINISTRADOR,
                        activo=True,
                        cuenta__is_active=True,
                    )
                    .values_list("pk", flat=True)
                )
                if len(administradores_activos) <= 1:
                    return Response(
                        {
                            "activo": (
                                "No se puede desactivar al último administrador activo."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            estado_anterior = perfil.activo and perfil.cuenta.is_active
            perfil.activo = nuevo_estado
            perfil.save(update_fields=["activo", "actualizado_en"])
            perfil.cuenta.is_active = nuevo_estado
            perfil.cuenta.save(update_fields=["is_active"])
            LogAuditoria.objects.create(
                usuario=actor,
                corredor=perfil.corredor,
                entidad="Usuario",
                id_registro=perfil.pk,
                accion=LogAuditoria.Accion.ADMIN_USUARIO,
                valor_anterior={"activo": estado_anterior},
                valor_nuevo={"activo": nuevo_estado},
                metodo="ACTIVAR" if nuevo_estado else "DESACTIVAR",
            )

        return Response(UsuariosAdminView._representar(perfil))


class RestablecerClaveTemporalView(APIView):
    permission_classes = [IsAuthenticated, SoloAdministradorPermission]

    def post(self, request, pk):
        clave_temporal = secrets.token_urlsafe(24)
        with transaction.atomic():
            perfil = (
                Usuario.objects.select_for_update(of=("self",))
                .select_related("cuenta", "rol", "corredor")
                .filter(pk=pk)
                .first()
            )
            if perfil is None:
                return Response(
                    {"detalle": "No se encontró el usuario."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if perfil.pk == request.nuam_profile.pk:
                return Response(
                    {
                        "detalle": (
                            "No puedes restablecer tu propia contraseña desde esta "
                            "pantalla."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not perfil.activo or not perfil.cuenta.is_active:
                return Response(
                    {"detalle": "Activa la cuenta antes de restablecer su acceso."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            debe_cambiar_antes = perfil.debe_cambiar_clave
            perfil.cuenta.set_password(clave_temporal)
            perfil.cuenta.save(update_fields=["password"])
            perfil.debe_cambiar_clave = True
            perfil.save(update_fields=["debe_cambiar_clave", "actualizado_en"])
            for token in OutstandingToken.objects.filter(user=perfil.cuenta):
                BlacklistedToken.objects.get_or_create(token=token)
            LogAuditoria.objects.create(
                usuario=request.nuam_profile,
                corredor=perfil.corredor,
                entidad="Usuario",
                id_registro=perfil.pk,
                accion=LogAuditoria.Accion.ADMIN_USUARIO,
                valor_anterior={"debe_cambiar_clave": debe_cambiar_antes},
                valor_nuevo={"debe_cambiar_clave": True},
                metodo="RESTABLECER_CLAVE",
            )

        return Response(
            {
                **UsuariosAdminView._representar(perfil),
                "clave_temporal": clave_temporal,
            },
            status=status.HTTP_200_OK,
        )
