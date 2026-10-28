from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Mercado(models.Model):
    codigo = models.CharField(max_length=3, unique=True)
    nombre = models.CharField(max_length=50)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Instrumento(models.Model):
    class TipoSociedad(models.TextChoices):
        ABIERTA = "A", "Abierta"
        CERRADA = "C", "Cerrada"

    mercado = models.ForeignKey(
        Mercado, on_delete=models.PROTECT, related_name="instrumentos"
    )
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=100)
    inscrito = models.BooleanField(default=True)
    tipo_sociedad = models.CharField(
        max_length=1, choices=TipoSociedad.choices, blank=True
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["mercado", "codigo"], name="instrumento_mercado_codigo_uniq"
            ),
        ]

    def __str__(self):
        return f"{self.codigo} ({self.mercado.codigo})"


class OrigenInformacion(models.Model):
    class Codigo(models.TextChoices):
        ARCHIVO_CARGA = "ARCHIVO_CARGA", "Archivo de carga"
        INGRESO_MANUAL = "INGRESO_MANUAL", "Ingreso manual"
        SISTEMA = "SISTEMA", "Sistema"

    codigo = models.CharField(max_length=20, unique=True, choices=Codigo.choices)
    descripcion = models.CharField(max_length=100)

    class Meta:
        ordering = ["codigo"]

    def __str__(self):
        return self.descripcion


class ColumnaTributaria(models.Model):
    class TipoDato(models.TextChoices):
        MONTO = "MONTO", "Monto"
        TASA = "TASA", "Tasa"

    nro_columna = models.PositiveSmallIntegerField(
        primary_key=True, validators=[MinValueValidator(8), MaxValueValidator(37)]
    )
    nombre_homologado = models.CharField(max_length=250)
    tipo_dato = models.CharField(
        max_length=10,
        choices=TipoDato.choices,
        default=TipoDato.MONTO,
    )
    grupo = models.CharField(max_length=80, blank=True)
    formula = models.CharField(max_length=200, blank=True)
    pendiente_homologacion = models.BooleanField(default=False)
    reglas_provisionales = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nro_columna"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(nro_columna__gte=8, nro_columna__lte=37),
                name="columna_tributaria_rango_8_37",
            ),
        ]

    def __str__(self):
        return f"{self.nro_columna}: {self.nombre_homologado}"
