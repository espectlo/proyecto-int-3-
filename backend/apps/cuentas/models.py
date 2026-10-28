from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Rol(models.Model):
    class Codigo(models.TextChoices):
        CORREDOR = "CORREDOR", "Corredor"
        OPERADOR_BOLSA = "OPERADOR_BOLSA", "Operador de Bolsa"
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
        AUDITOR = "AUDITOR", "Auditor"

    codigo = models.CharField(max_length=30, unique=True, choices=Codigo.choices)
    nombre = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "rol"
        verbose_name_plural = "roles"

    def __str__(self):
        return self.nombre


class Corredor(models.Model):
    rut = models.CharField(max_length=12, unique=True)
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Usuario(models.Model):
    cuenta = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="perfil_nuam",
    )
    email = models.EmailField(unique=True, max_length=120)
    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,
        related_name="usuarios",
    )
    corredor = models.ForeignKey(
        Corredor,
        on_delete=models.PROTECT,
        related_name="usuarios",
        null=True,
        blank=True,
    )
    activo = models.BooleanField(default=True)
    debe_cambiar_clave = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["email"]
        constraints = [
            models.CheckConstraint(
                condition=Q(intentos_fallidos__lte=5),
                name="usuario_intentos_fallidos_max_5",
            ),
        ]

    def clean(self):
        super().clean()
        if self.rol_id and self.rol.codigo == Rol.Codigo.CORREDOR:
            if not self.corredor_id:
                raise ValidationError(
                    {"corredor": "Un usuario corredor debe tener un corredor asignado."}
                )
        elif self.corredor_id:
            raise ValidationError(
                {
                    "corredor": (
                        "Solo los usuarios con rol corredor tienen un corredor "
                        "asignado."
                    )
                }
            )

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)
