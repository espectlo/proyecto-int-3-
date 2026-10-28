from django.db import models

from apps.cuentas.models import Corredor


class LogAuditoria(models.Model):
    class Accion(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso"
        MODIFICACION = "MODIFICACION", "Modificación"
        ELIMINACION = "ELIMINACION", "Eliminación"
        CARGA = "CARGA", "Carga"
        ACCESO_DENEGADO = "ACCESO_DENEGADO", "Acceso denegado"
        CONSULTA_AUDITOR = "CONSULTA_AUDITOR", "Consulta de auditor"
        ADMIN_USUARIO = "ADMIN_USUARIO", "Administración de usuario"
        CAMBIO_CLAVE = "CAMBIO_CLAVE", "Cambio de contraseña"

    usuario = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
    )
    corredor = models.ForeignKey(
        Corredor,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
        null=True,
        blank=True,
    )
    entidad = models.CharField(max_length=40)
    id_registro = models.BigIntegerField()
    accion = models.CharField(max_length=20, choices=Accion.choices)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    valor_anterior = models.JSONField(null=True, blank=True)
    valor_nuevo = models.JSONField(null=True, blank=True)
    metodo = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["-fecha_hora", "-id"]
        indexes = [
            models.Index(
                fields=["usuario", "fecha_hora"],
                name="auditoria_usuario_fecha_idx",
            ),
            models.Index(
                fields=["entidad", "id_registro"],
                name="auditoria_entidad_reg_idx",
            ),
            models.Index(
                fields=["accion", "fecha_hora"],
                name="auditoria_accion_fecha_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Los registros de auditoría son inmutables.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Los registros de auditoría no se pueden eliminar.")

    def __str__(self):
        return f"{self.accion} · {self.entidad} #{self.id_registro}"
