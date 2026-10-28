from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.cuentas.models import Corredor


class CargaMasiva(models.Model):
    class Tipo(models.TextChoices):
        FACTORES = "FACTORES", "Factores"
        MONTOS = "MONTOS", "Montos"

    class Formato(models.TextChoices):
        CSV = "CSV", "CSV"
        XLSX = "XLSX", "Excel"
        XML = "XML", "XML"

    class Estado(models.TextChoices):
        PREVISUALIZADA = "PREVISUALIZADA", "Previsualizada"
        PENDIENTE_MONGO = "PENDIENTE_MONGO", "Pendiente de MongoDB"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        FALLIDA = "FALLIDA", "Fallida"
        CANCELADA = "CANCELADA", "Cancelada"

    corredor = models.ForeignKey(
        Corredor,
        on_delete=models.PROTECT,
        related_name="cargas",
        null=True,
        blank=True,
    )
    usuario = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.PROTECT,
        related_name="cargas",
    )
    tipo_carga = models.CharField(max_length=10, choices=Tipo.choices)
    nombre_archivo = models.CharField(max_length=200)
    formato = models.CharField(max_length=4, choices=Formato.choices)
    hoja = models.CharField(max_length=100, null=True, blank=True)
    encabezados_detectados = models.JSONField(default=list, blank=True)
    tamano_bytes = models.PositiveBigIntegerField(
        validators=[MaxValueValidator(50 * 1024 * 1024)]
    )
    sha256_archivo = models.CharField(max_length=64)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PREVISUALIZADA
    )
    total_filas = models.PositiveIntegerField(default=0)
    filas_ok = models.PositiveIntegerField(default=0)
    filas_error = models.PositiveIntegerField(default=0)
    vencimiento_previsualizacion = models.DateTimeField(null=True, blank=True)
    confirmada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_hora"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tamano_bytes__lte=50 * 1024 * 1024),
                name="carga_masiva_tamano_max_50mb",
            ),
            models.CheckConstraint(
                condition=models.Q(filas_ok__lte=models.F("total_filas")),
                name="carga_filas_ok_menor_igual_total",
            ),
            models.CheckConstraint(
                condition=models.Q(filas_error__lte=models.F("total_filas")),
                name="carga_filas_error_menor_igual_total",
            ),
        ]
        indexes = [
            models.Index(
                fields=["corredor", "fecha_hora"],
                name="carga_corredor_fecha_idx",
            ),
            models.Index(
                fields=["sha256_archivo", "usuario"],
                name="carga_hash_usuario_idx",
            ),
        ]

    def __str__(self):
        return f"{self.nombre_archivo} ({self.estado})"


class DetalleCarga(models.Model):
    class EstadoFila(models.TextChoices):
        VALIDA = "VALIDA", "Válida"
        RECHAZADA = "RECHAZADA", "Rechazada"
        PROCESADA = "PROCESADA", "Procesada"

    carga = models.ForeignKey(
        CargaMasiva, on_delete=models.CASCADE, related_name="detalles"
    )
    nro_fila = models.PositiveIntegerField()
    estado_fila = models.CharField(max_length=15, choices=EstadoFila.choices)
    mensaje_error = models.CharField(max_length=300, blank=True)
    contenido_original = models.JSONField(default=dict, blank=True)
    datos_normalizados = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["nro_fila"]
        constraints = [
            models.UniqueConstraint(
                fields=["carga", "nro_fila"], name="detalle_carga_fila_uniq"
            ),
        ]

    def __str__(self):
        return f"Carga {self.carga_id}, fila {self.nro_fila}"


class OutboxCarga(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        COMPENSAR = "COMPENSAR", "Compensación pendiente"
        PROCESADA = "PROCESADA", "Procesada"
        FALLIDA = "FALLIDA", "Fallida"

    carga = models.OneToOneField(
        CargaMasiva,
        on_delete=models.CASCADE,
        related_name="outbox",
    )
    payload = models.JSONField(default=dict)
    sha256_payload = models.CharField(max_length=64)
    estado = models.CharField(
        max_length=15,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    intentos = models.PositiveIntegerField(default=0)
    proximo_intento = models.DateTimeField(default=timezone.now)
    ultimo_error = models.CharField(max_length=200, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    procesado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["creado_en"]
        indexes = [
            models.Index(
                fields=["estado", "proximo_intento"],
                name="outbox_carga_estado_next_idx",
            ),
        ]
