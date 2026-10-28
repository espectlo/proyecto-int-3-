from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.cuentas.models import Corredor

from .catalogos import ColumnaTributaria, Instrumento, OrigenInformacion


class Calificacion(models.Model):
    class Estado(models.TextChoices):
        VIGENTE = "VIGENTE", "Vigente"
        ELIMINADA = "ELIMINADA", "Eliminada"

    class MetodoActualizacion(models.TextChoices):
        INGRESO_MANUAL = "INGRESO_MANUAL", "Ingreso manual"
        CARGA_FACTORES = "CARGA_FACTORES", "Carga de factores"
        CARGA_MONTOS = "CARGA_MONTOS", "Carga de montos"
        SISTEMA = "SISTEMA", "Sistema"

    corredor = models.ForeignKey(
        Corredor,
        on_delete=models.PROTECT,
        related_name="calificaciones",
        null=True,
        blank=True,
    )
    instrumento = models.ForeignKey(
        Instrumento, on_delete=models.PROTECT, related_name="calificaciones"
    )
    origen = models.ForeignKey(
        OrigenInformacion, on_delete=models.PROTECT, related_name="calificaciones"
    )
    usuario = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.PROTECT,
        related_name="calificaciones",
    )
    carga = models.ForeignKey(
        "calificaciones.CargaMasiva",
        on_delete=models.PROTECT,
        related_name="calificaciones",
        null=True,
        blank=True,
    )
    ejercicio = models.PositiveSmallIntegerField()
    secuencia_evento = models.PositiveBigIntegerField()
    numero_dividendo = models.PositiveBigIntegerField(default=0)
    fecha_pago = models.DateField()
    descripcion_dividendo = models.CharField(max_length=200, blank=True)
    valor_historico = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    isfut = models.BooleanField(default=False)
    factor_actualizacion = models.DecimalField(
        max_digits=9, decimal_places=8, default=0
    )
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.VIGENTE
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_ultima_modificacion = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)
    metodo_actualizacion = models.CharField(
        max_length=30,
        choices=MetodoActualizacion.choices,
        default=MetodoActualizacion.INGRESO_MANUAL,
    )
    eliminada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-ejercicio", "-fecha_pago", "instrumento__codigo"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ejercicio__gte=1900, ejercicio__lte=2200),
                name="calificacion_ejercicio_rango",
            ),
            models.CheckConstraint(
                condition=Q(factor_actualizacion__gte=0, factor_actualizacion__lte=1),
                name="calificacion_factor_actualizacion_rango",
            ),
            models.UniqueConstraint(
                fields=[
                    "ejercicio",
                    "instrumento",
                    "fecha_pago",
                    "secuencia_evento",
                ],
                condition=Q(corredor__isnull=True, estado="VIGENTE"),
                name="calif_bolsa_llave_vigente_uniq",
            ),
            models.UniqueConstraint(
                fields=[
                    "corredor",
                    "ejercicio",
                    "instrumento",
                    "fecha_pago",
                    "secuencia_evento",
                ],
                condition=Q(corredor__isnull=False, estado="VIGENTE"),
                name="calif_corredor_llave_vigente_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["corredor", "estado", "ejercicio"],
                name="calif_corredor_estado_ejer_idx",
            ),
            models.Index(
                fields=["instrumento", "fecha_pago"], name="calif_instr_fecha_idx"
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.origen_id
            and self.origen.codigo == OrigenInformacion.Codigo.INGRESO_MANUAL
            and self.secuencia_evento <= 10000
        ):
            raise ValidationError(
                {
                    "secuencia_evento": (
                        "La secuencia de ingreso manual debe ser mayor a 10.000."
                    )
                }
            )

    def __str__(self):
        return f"{self.instrumento.codigo} · {self.ejercicio} · {self.secuencia_evento}"


class MontoCalificacion(models.Model):
    calificacion = models.ForeignKey(
        Calificacion, on_delete=models.CASCADE, related_name="montos"
    )
    columna = models.ForeignKey(
        ColumnaTributaria, on_delete=models.PROTECT, related_name="montos"
    )
    monto = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["calificacion", "columna"], name="monto_calificacion_col_uniq"
            ),
            models.CheckConstraint(
                condition=Q(monto__gte=0), name="monto_calificacion_no_negativo"
            ),
        ]


class FactorCalificacion(models.Model):
    calificacion = models.ForeignKey(
        Calificacion, on_delete=models.CASCADE, related_name="factores"
    )
    columna = models.ForeignKey(
        ColumnaTributaria, on_delete=models.PROTECT, related_name="factores"
    )
    valor = models.DecimalField(max_digits=9, decimal_places=8)
    editado_manual = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["calificacion", "columna"],
                name="factor_calificacion_col_uniq",
            ),
            models.CheckConstraint(
                condition=Q(valor__gte=0, valor__lte=1),
                name="factor_calificacion_rango",
            ),
        ]
