from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import TestCase
from django.core.management import call_command

from apps.calificaciones.models import (
    Calificacion,
    ColumnaTributaria,
    FactorCalificacion,
    LogAuditoria,
    Mercado,
    MontoCalificacion,
    OrigenInformacion,
)
from apps.cuentas.models import Corredor, Rol, Usuario


class ModelosCalificacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_corredor = Rol.objects.create(
            codigo=Rol.Codigo.CORREDOR, nombre="Corredor"
        )
        cls.corredor = Corredor.objects.create(rut="76.000.000-0", nombre="Corredora A")
        cls.cuenta = get_user_model().objects.create_user(
            username="corredor",
            email="corredor@example.test",
            password="Clave-local-123!",
        )
        cls.usuario = Usuario.objects.create(
            cuenta=cls.cuenta,
            email=cls.cuenta.email,
            rol=cls.rol_corredor,
            corredor=cls.corredor,
        )
        cls.mercado = Mercado.objects.create(codigo="ACN", nombre="Acciones")
        cls.instrumento = cls.mercado.instrumentos.create(
            codigo="COPEC", nombre="Copec"
        )
        cls.origen = OrigenInformacion.objects.create(
            codigo=OrigenInformacion.Codigo.INGRESO_MANUAL,
            descripcion="Ingreso manual",
        )
        cls.columnas = [
            ColumnaTributaria.objects.create(
                nro_columna=nro, nombre_homologado=f"Columna {nro}"
            )
            for nro in (8, 9, 20)
        ]

    def crear_calificacion(self, secuencia=10001, corredor=None, estado="VIGENTE"):
        return Calificacion.objects.create(
            corredor=corredor or self.corredor,
            instrumento=self.instrumento,
            origen=self.origen,
            usuario=self.usuario,
            ejercicio=2025,
            secuencia_evento=secuencia,
            fecha_pago=date(2025, 5, 12),
            estado=estado,
        )

    def test_usuario_corredor_requiere_corredor(self):
        cuenta = get_user_model().objects.create_user(
            username="sin-corredor",
            email="sin-corredor@example.test",
            password="Clave-local-123!",
        )
        usuario = Usuario(
            cuenta=cuenta,
            email=cuenta.email,
            rol=self.rol_corredor,
        )
        with self.assertRaises(ValidationError):
            usuario.full_clean()

    def test_ingreso_manual_exige_secuencia_mayor_a_10000(self):
        calificacion = Calificacion(
            corredor=self.corredor,
            instrumento=self.instrumento,
            origen=self.origen,
            usuario=self.usuario,
            ejercicio=2025,
            secuencia_evento=10000,
            fecha_pago=date(2025, 5, 12),
        )
        with self.assertRaises(ValidationError):
            calificacion.full_clean()

    def test_llave_unica_local_y_llave_independiente_de_bolsa(self):
        self.crear_calificacion()
        calificacion_bolsa = Calificacion.objects.create(
            corredor=None,
            instrumento=self.instrumento,
            origen=self.origen,
            usuario=self.usuario,
            ejercicio=2025,
            secuencia_evento=10001,
            fecha_pago=date(2025, 5, 12),
        )
        self.assertIsNone(calificacion_bolsa.corredor_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_calificacion()

    def test_calificacion_eliminada_libera_llave_para_reingreso(self):
        self.crear_calificacion(estado=Calificacion.Estado.ELIMINADA)
        vigente = self.crear_calificacion()
        self.assertEqual(vigente.estado, Calificacion.Estado.VIGENTE)

    def test_montos_negativos_se_rechazan_en_base_de_datos(self):
        calificacion = self.crear_calificacion()
        with self.assertRaises(IntegrityError), transaction.atomic():
            MontoCalificacion.objects.create(
                calificacion=calificacion,
                columna=self.columnas[0],
                monto=Decimal("-1"),
            )

    def test_factor_fuera_de_rango_se_rechaza_en_base_de_datos(self):
        calificacion = self.crear_calificacion()
        with self.assertRaises(IntegrityError), transaction.atomic():
            FactorCalificacion.objects.create(
                calificacion=calificacion,
                columna=self.columnas[0],
                valor=Decimal("1.00000001"),
            )

    def test_columnas_tributarias_fuera_del_rango_se_rechazan(self):
        columna = ColumnaTributaria(
            nro_columna=38, nombre_homologado="Fuera de rango"
        )
        with self.assertRaises(ValidationError):
            columna.full_clean()

    def test_auditoria_no_permite_edicion_ni_eliminacion(self):
        evento = LogAuditoria.objects.create(
            usuario=self.usuario,
            entidad="Calificacion",
            id_registro=1,
            accion=LogAuditoria.Accion.INGRESO,
        )
        evento.metodo = "CAMBIO"
        with self.assertRaises(ValueError):
            evento.save()
        with self.assertRaises(ValueError):
            evento.delete()

    def test_auditoria_no_se_puede_editar_directamente_en_base_de_datos(self):
        evento = LogAuditoria.objects.create(
            usuario=self.usuario,
            entidad="Calificacion",
            id_registro=2,
            accion=LogAuditoria.Accion.MODIFICACION,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            LogAuditoria.objects.filter(pk=evento.pk).update(metodo="ALTERACION")

    def test_auditoria_no_se_puede_eliminar_directamente_en_base_de_datos(self):
        evento = LogAuditoria.objects.create(
            usuario=self.usuario,
            entidad="Calificacion",
            id_registro=3,
            accion=LogAuditoria.Accion.ELIMINACION,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            LogAuditoria.objects.filter(pk=evento.pk).delete()

    def test_auditoria_no_se_puede_truncar_en_base_de_datos(self):
        LogAuditoria.objects.create(
            usuario=self.usuario,
            entidad="Calificacion",
            id_registro=4,
            accion=LogAuditoria.Accion.ELIMINACION,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE calificaciones_logauditoria")


class CatalogoSemillaTests(TestCase):
    def test_comando_semilla_es_idempotente(self):
        call_command("sembrar_catalogos", verbosity=0)
        call_command("sembrar_catalogos", verbosity=0)

        self.assertEqual(Rol.objects.count(), 4)
        self.assertEqual(Mercado.objects.count(), 3)
        self.assertEqual(OrigenInformacion.objects.count(), 3)
        self.assertEqual(ColumnaTributaria.objects.count(), 30)
        self.assertEqual(
            ColumnaTributaria.objects.filter(pendiente_homologacion=True).count(),
            0,
        )
        self.assertEqual(
            ColumnaTributaria.objects.filter(reglas_provisionales=True).count(),
            4,
        )
