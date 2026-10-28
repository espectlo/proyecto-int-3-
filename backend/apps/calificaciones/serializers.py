from rest_framework import serializers

from .models import (
    Calificacion,
    FactorCalificacion,
    MontoCalificacion,
)


class MontoCalificacionSerializer(serializers.ModelSerializer):
    columna = serializers.IntegerField(source="columna_id", read_only=True)

    class Meta:
        model = MontoCalificacion
        fields = ["columna", "monto"]


class FactorCalificacionSerializer(serializers.ModelSerializer):
    columna = serializers.IntegerField(source="columna_id", read_only=True)

    class Meta:
        model = FactorCalificacion
        fields = ["columna", "valor", "editado_manual"]


class CalificacionSerializer(serializers.ModelSerializer):
    codigo_instrumento = serializers.CharField(
        source="instrumento.codigo",
        read_only=True,
    )
    nombre_instrumento = serializers.CharField(
        source="instrumento.nombre",
        read_only=True,
    )
    mercado_codigo = serializers.CharField(
        source="instrumento.mercado.codigo",
        read_only=True,
    )
    mercado_nombre = serializers.CharField(
        source="instrumento.mercado.nombre",
        read_only=True,
    )
    origen_codigo = serializers.CharField(source="origen.codigo", read_only=True)
    corredor_nombre = serializers.CharField(
        source="corredor.nombre",
        read_only=True,
        default=None,
    )
    montos = MontoCalificacionSerializer(many=True, read_only=True)
    factores = FactorCalificacionSerializer(many=True, read_only=True)
    version = serializers.IntegerField(required=False)

    class Meta:
        model = Calificacion
        fields = [
            "id",
            "instrumento",
            "codigo_instrumento",
            "nombre_instrumento",
            "mercado_codigo",
            "mercado_nombre",
            "corredor",
            "corredor_nombre",
            "origen_codigo",
            "ejercicio",
            "secuencia_evento",
            "numero_dividendo",
            "fecha_pago",
            "descripcion_dividendo",
            "valor_historico",
            "isfut",
            "factor_actualizacion",
            "estado",
            "metodo_actualizacion",
            "version",
            "fecha_creacion",
            "fecha_ultima_modificacion",
            "montos",
            "factores",
        ]
        read_only_fields = [
            "id",
            "corredor",
            "origen_codigo",
            "estado",
            "metodo_actualizacion",
            "fecha_creacion",
            "fecha_ultima_modificacion",
            "version",
        ]

    def validate_ejercicio(self, value):
        if not 1900 <= value <= 2200:
            raise serializers.ValidationError(
                "El ejercicio debe estar entre 1900 y 2200."
            )
        return value

    def validate_factor_actualizacion(self, value):
        if value < 0 or value > 1:
            raise serializers.ValidationError(
                "El factor de actualización debe estar entre 0 y 1."
            )
        return value

    def validate_instrumento(self, value):
        if not value.activo:
            raise serializers.ValidationError("El instrumento no está activo.")
        return value

    def validate(self, attrs):
        perfil = self.context["request"].nuam_profile
        if (
            self.instance is None
            and perfil.rol.codigo in ("CORREDOR", "OPERADOR_BOLSA")
            and attrs.get("secuencia_evento", 0) <= 10000
        ):
            raise serializers.ValidationError(
                {"secuencia_evento": "Debe ser mayor a 10.000."}
            )
        return attrs
