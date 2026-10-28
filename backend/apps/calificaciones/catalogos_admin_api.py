from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cuentas.permissions import SoloAdministradorPermission

from .models import ColumnaTributaria, LogAuditoria


class ColumnaTributariaSerializer(serializers.Serializer):
    nombre_homologado = serializers.CharField(max_length=250, required=False)
    tipo_dato = serializers.ChoiceField(
        choices=ColumnaTributaria.TipoDato.choices,
        required=False,
    )
    formula = serializers.CharField(max_length=200, allow_blank=True, required=False)
    reglas_provisionales = serializers.BooleanField(required=False)


class ColumnaTributariaAdminView(APIView):
    permission_classes = [IsAuthenticated, SoloAdministradorPermission]

    def patch(self, request, pk):
        serializer = ColumnaTributariaSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        cambios = serializer.validated_data
        if not cambios:
            return Response(
                {"detalle": "Indica al menos un campo para actualizar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            columna = (
                ColumnaTributaria.objects.select_for_update()
                .filter(pk=pk)
                .first()
            )
            if columna is None:
                return Response(
                    {"detalle": "No se encontró la columna tributaria."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            valor_anterior = {
                campo: getattr(columna, campo)
                for campo in cambios
            }
            for campo, valor in cambios.items():
                setattr(columna, campo, valor)
            columna.save(update_fields=list(cambios))
            valor_nuevo = {
                campo: getattr(columna, campo)
                for campo in cambios
            }
            LogAuditoria.objects.create(
                usuario=request.nuam_profile,
                entidad="ColumnaTributaria",
                id_registro=columna.pk,
                accion=LogAuditoria.Accion.MODIFICACION,
                valor_anterior=valor_anterior,
                valor_nuevo=valor_nuevo,
                metodo="ACTUALIZAR_CATALOGO",
            )

        return Response(
            {
                "nro_columna": columna.pk,
                "nombre_homologado": columna.nombre_homologado,
                "tipo_dato": columna.tipo_dato,
                "formula": columna.formula,
                "pendiente_homologacion": columna.pendiente_homologacion,
                "reglas_provisionales": columna.reglas_provisionales,
            }
        )
