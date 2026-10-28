import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone
from pymongo import UpdateOne
from pymongo.errors import PyMongoError

from apps.calificaciones.models import (
    Calificacion,
    CargaMasiva,
    ColumnaTributaria,
    DetalleCarga,
    FactorCalificacion,
    Instrumento,
    LogAuditoria,
    MontoCalificacion,
    OrigenInformacion,
    OutboxCarga,
)

from .calculo import calcular_factores, validar_suma_factores
from .cargas_integridad import _claves_existentes, _hash_payload

logger = logging.getLogger(__name__)
TAMANO_LOTE_MONGO = 500


class InconsistenciaMongo(Exception):
    pass


def _documentos_mongo(outbox):
    return [
        {
            "_id": f"{outbox.carga_id}:{fila['nro_fila']}",
            "id_carga": outbox.carga_id,
            "nro_fila": fila["nro_fila"],
            "tipo_carga": outbox.payload["tipo"],
            "sha256_payload": outbox.sha256_payload,
            "datos": fila["datos"],
        }
        for fila in outbox.payload["filas"]
    ]


def _documentos_rechazados(outbox, errores_override=None):
    carga = outbox.carga
    ahora = carga.fecha_hora
    return [
        {
            "id_carga": outbox.carga_id,
            "id_corredor": carga.corredor_id,
            "fila": fila["nro_fila"],
            "contenido_original": fila.get("contenido_original", fila["datos"]),
            "errores": errores_override or fila.get("errores", []),
            "creado_en": ahora,
        }
        for fila in outbox.payload["filas"]
        if errores_override or fila.get("errores")
    ]


def _guardar_metadatos(collection, outbox, total_rechazadas):
    carga = outbox.carga
    documento = {
        "id_carga": carga.pk,
        "id_corredor": carga.corredor_id,
        "archivo": carga.nombre_archivo,
        "formato": carga.formato,
        "hoja": carga.hoja,
        "encabezados_detectados": outbox.payload.get(
            "encabezados_detectados",
            carga.encabezados_detectados,
        ),
        "total_filas": carga.total_filas,
        "total_rechazadas": total_rechazadas,
        "sha256_payload": outbox.sha256_payload,
        "creado_en": carga.fecha_hora,
    }
    collection.update_one(
        {"id_carga": carga.pk},
        {"$setOnInsert": documento},
        upsert=True,
    )
    existente = collection.find_one(
        {"id_carga": carga.pk},
        {"_id": 0, "sha256_payload": 1},
    )
    if existente and existente.get("sha256_payload") != outbox.sha256_payload:
        raise InconsistenciaMongo(
            "La carga ya tiene metadatos asociados a otro hash."
        )
    if total_rechazadas:
        collection.update_one(
            {"id_carga": carga.pk},
            {"$set": {"total_rechazadas": total_rechazadas}},
        )


def _guardar_rechazadas(collection, outbox, errores_override=None):
    documentos = _documentos_rechazados(outbox, errores_override)
    if documentos:
        collection.bulk_write(
            [
                UpdateOne(
                    {
                        "id_carga": documento["id_carga"],
                        "fila": documento["fila"],
                    },
                    {"$setOnInsert": documento},
                    upsert=True,
                )
                for documento in documentos
            ],
            ordered=False,
        )
        esperados = {
            (documento["id_carga"], documento["fila"]): documento
            for documento in documentos
        }
        existentes = {
            (documento["id_carga"], documento["fila"]): documento
            for documento in collection.find(
                {
                    "id_carga": outbox.carga_id,
                    "fila": {"$in": [documento["fila"] for documento in documentos]},
                },
                {
                    "id_carga": 1,
                    "id_corredor": 1,
                    "fila": 1,
                    "contenido_original": 1,
                    "errores": 1,
                },
            )
        }
        if set(existentes) != set(esperados) or any(
            any(
                existentes[clave].get(campo) != documento[campo]
                for campo in (
                    "id_corredor",
                    "contenido_original",
                    "errores",
                )
            )
            for clave, documento in esperados.items()
        ):
            raise InconsistenciaMongo(
                "MongoDB ya contiene rechazos diferentes para esta carga."
            )


def _escribir_mongo(collection, outbox):
    rechazadas = _documentos_rechazados(outbox)
    _guardar_metadatos(
        collection.database["cargas_detalle"],
        outbox,
        len(rechazadas),
    )
    _guardar_rechazadas(
        collection.database["cargas_filas_rechazadas"],
        outbox,
    )
    if outbox.payload.get("operacion") == "VALIDACION_RECHAZOS":
        return
    documentos = _documentos_mongo(outbox)
    for inicio in range(0, len(documentos), TAMANO_LOTE_MONGO):
        grupo = documentos[inicio:inicio + TAMANO_LOTE_MONGO]
        collection.bulk_write(
            [
                UpdateOne(
                    {"_id": documento["_id"]},
                    {"$setOnInsert": documento},
                    upsert=True,
                )
                for documento in grupo
            ],
            ordered=False,
        )
        encontrados = {
            documento["_id"]: documento.get("sha256_payload")
            for documento in collection.find(
                {
                    "_id": {"$in": [documento["_id"] for documento in grupo]},
                    "id_carga": outbox.carga_id,
                },
                {"_id": 1, "sha256_payload": 1},
            )
        }
        if any(
            encontrados.get(documento["_id"]) != outbox.sha256_payload
            for documento in grupo
        ):
            raise InconsistenciaMongo(
                "La carga ya tiene documentos con un hash diferente."
            )


def _claves_payload(outbox):
    instrumentos = {
        (instrumento.mercado.codigo.upper(), instrumento.codigo.upper()): instrumento.pk
        for instrumento in Instrumento.objects.filter(
            mercado__codigo__in=[
                fila["datos"]["mercado"] for fila in outbox.payload["filas"]
            ],
            codigo__in=[
                fila["datos"]["codigo_instrumento"]
                for fila in outbox.payload["filas"]
            ],
        ).select_related("mercado")
    }
    return [
        (
            instrumentos[
                (
                    fila["datos"]["mercado"].upper(),
                    fila["datos"]["codigo_instrumento"].upper(),
                )
            ],
            int(fila["datos"]["ejercicio"]),
            date.fromisoformat(fila["datos"]["fecha_pago"]),
            int(fila["datos"]["secuencia_evento"]),
        )
        for fila in outbox.payload["filas"]
    ]


def _persistir_postgres(outbox):
    carga = CargaMasiva.objects.select_related("usuario", "corredor").get(
        pk=outbox.carga_id
    )
    tipo = outbox.payload["tipo"]
    if tipo not in (CargaMasiva.Tipo.MONTOS, CargaMasiva.Tipo.FACTORES):
        raise ValueError("El tipo de carga del outbox no es válido.")

    filas = outbox.payload["filas"]
    codigos = {
        (fila["datos"]["mercado"].upper(), fila["datos"]["codigo_instrumento"].upper())
        for fila in filas
    }
    instrumentos = {
        (instrumento.mercado.codigo.upper(), instrumento.codigo.upper()): instrumento
        for instrumento in Instrumento.objects.filter(
            mercado__codigo__in={codigo[0] for codigo in codigos},
            codigo__in={codigo[1] for codigo in codigos},
        ).select_related("mercado")
    }
    columnas = ColumnaTributaria.objects.in_bulk(range(8, 38))
    if len(columnas) != 30:
        raise ValueError("El catálogo de columnas tributarias está incompleto.")
    origen = OrigenInformacion.objects.get(
        codigo=OrigenInformacion.Codigo.ARCHIVO_CARGA
    )

    calificaciones = []
    datos_por_fila = []
    for fila in filas:
        datos = fila["datos"]
        instrumento = instrumentos.get(
            (datos["mercado"].upper(), datos["codigo_instrumento"].upper())
        )
        if instrumento is None:
            raise ValueError("Un instrumento de la carga ya no existe.")
        montos = {
            numero: Decimal(datos.get(f"monto_{numero}") or "0")
            for numero in range(8, 38)
        }
        if tipo == CargaMasiva.Tipo.MONTOS:
            factores = calcular_factores(montos, base_desde=8, base_hasta=19)
            montos_a_guardar = {
                numero: Decimal(datos[f"monto_{numero}"])
                for numero in range(8, 38)
                if datos.get(f"monto_{numero}")
            }
        else:
            factores = {
                numero: Decimal(datos[f"factor_{numero}"])
                for numero in range(8, 38)
                if datos.get(f"factor_{numero}")
            }
            validar_suma_factores(factores, desde=8, hasta=16)
            montos_a_guardar = {}
        calificaciones.append(
            Calificacion(
                corredor=carga.corredor,
                instrumento=instrumento,
                origen=origen,
                usuario=carga.usuario,
                carga=carga,
                ejercicio=int(datos["ejercicio"]),
                secuencia_evento=int(datos["secuencia_evento"]),
                numero_dividendo=int(datos["numero_dividendo"]),
                fecha_pago=date.fromisoformat(datos["fecha_pago"]),
                descripcion_dividendo=datos["descripcion_dividendo"],
                metodo_actualizacion=(
                    Calificacion.MetodoActualizacion.CARGA_MONTOS
                    if tipo == CargaMasiva.Tipo.MONTOS
                    else Calificacion.MetodoActualizacion.CARGA_FACTORES
                ),
            )
        )
        datos_por_fila.append((montos_a_guardar, factores))

    Calificacion.objects.bulk_create(calificaciones, batch_size=TAMANO_LOTE_MONGO)
    if any(calificacion.pk is None for calificacion in calificaciones):
        raise RuntimeError("La base no devolvió los identificadores de calificación.")

    montos_a_guardar = []
    factores_a_guardar = []
    for calificacion, (montos, factores) in zip(calificaciones, datos_por_fila):
        montos_a_guardar.extend(
            MontoCalificacion(
                calificacion=calificacion,
                columna_id=numero,
                monto=monto,
            )
            for numero, monto in montos.items()
        )
        factores_a_guardar.extend(
            FactorCalificacion(
                calificacion=calificacion,
                columna_id=numero,
                valor=factor,
                editado_manual=False,
            )
            for numero, factor in factores.items()
        )
    MontoCalificacion.objects.bulk_create(
        montos_a_guardar, batch_size=TAMANO_LOTE_MONGO
    )
    FactorCalificacion.objects.bulk_create(
        factores_a_guardar, batch_size=TAMANO_LOTE_MONGO
    )

    ahora = timezone.now()
    carga.estado = CargaMasiva.Estado.CONFIRMADA
    carga.confirmada_en = ahora
    carga.filas_ok = len(calificaciones)
    carga.filas_error = 0
    carga.save(
        update_fields=["estado", "confirmada_en", "filas_ok", "filas_error"]
    )
    carga.detalles.update(
        estado_fila=DetalleCarga.EstadoFila.PROCESADA,
        contenido_original={},
    )
    outbox.estado = OutboxCarga.Estado.PROCESADA
    outbox.procesado_en = ahora
    outbox.payload = {}
    outbox.ultimo_error = ""
    outbox.save(
        update_fields=["estado", "procesado_en", "payload", "ultimo_error"]
    )
    LogAuditoria.objects.create(
        usuario=carga.usuario,
        corredor=carga.corredor,
        entidad="CargaMasiva",
        id_registro=carga.pk,
        accion=LogAuditoria.Accion.CARGA,
        valor_nuevo={
            "estado": carga.estado,
            "filas_ok": carga.filas_ok,
            "tipo": tipo,
            "sha256_payload": outbox.sha256_payload,
        },
        metodo="CONFIRMADA",
    )


def _programar_reintento(outbox, error):
    espera = min(2 ** min(outbox.intentos, 8), 300)
    outbox.estado = OutboxCarga.Estado.PENDIENTE
    outbox.ultimo_error = error[:200]
    outbox.proximo_intento = timezone.now() + timedelta(seconds=espera)
    outbox.save(
        update_fields=["estado", "ultimo_error", "proximo_intento"]
    )


def _programar_compensacion(outbox, error):
    outbox.estado = OutboxCarga.Estado.COMPENSAR
    outbox.ultimo_error = error[:200]
    outbox.proximo_intento = timezone.now()
    outbox.save(
        update_fields=["estado", "ultimo_error", "proximo_intento"]
    )


def _retrasar_compensacion(outbox):
    espera = min(2 ** min(outbox.intentos, 8), 300)
    outbox.proximo_intento = timezone.now() + timedelta(seconds=espera)
    outbox.save(update_fields=["proximo_intento"])


def _compensar(collection, outbox):
    filtro_carga = {"id_carga": outbox.carga_id}
    collection.delete_many(filtro_carga)
    collection.database["cargas_detalle"].delete_many(filtro_carga)
    collection.database["cargas_filas_rechazadas"].delete_many(filtro_carga)
    carga = outbox.carga
    mensaje_rechazo = (
        "La carga encontró una llave ya registrada."
        if outbox.ultimo_error == "CONFLICTO_LLAVE"
        else "La carga no pudo verificar la integridad de sus detalles."
    )
    errores_rechazo = [mensaje_rechazo]
    if _hash_payload(outbox.payload) == outbox.sha256_payload:
        rechazadas = _documentos_rechazados(outbox, errores_rechazo)
        _guardar_metadatos(
            collection.database["cargas_detalle"],
            outbox,
            len(rechazadas),
        )
        _guardar_rechazadas(
            collection.database["cargas_filas_rechazadas"],
            outbox,
            errores_rechazo,
        )
    carga.estado = CargaMasiva.Estado.FALLIDA
    carga.filas_ok = 0
    carga.filas_error = carga.total_filas
    carga.save(update_fields=["estado", "filas_ok", "filas_error"])
    carga.detalles.update(
        estado_fila=DetalleCarga.EstadoFila.RECHAZADA,
        mensaje_error=mensaje_rechazo,
        contenido_original={},
        datos_normalizados={},
    )
    outbox.estado = OutboxCarga.Estado.FALLIDA
    outbox.procesado_en = timezone.now()
    outbox.payload = {}
    outbox.save(
        update_fields=["estado", "procesado_en", "payload"]
    )
    LogAuditoria.objects.create(
        usuario=carga.usuario,
        corredor=carga.corredor,
        entidad="CargaMasiva",
        id_registro=carga.pk,
        accion=LogAuditoria.Accion.CARGA,
        valor_nuevo={
            "estado": carga.estado,
            "filas_error": carga.filas_error,
            "motivo": outbox.ultimo_error,
        },
        metodo="FALLIDA",
    )


def _finalizar_rechazos_validacion(outbox):
    carga = outbox.carga
    carga.estado = CargaMasiva.Estado.FALLIDA
    carga.confirmada_en = None
    carga.save(update_fields=["estado", "confirmada_en"])
    carga.detalles.update(contenido_original={}, datos_normalizados={})
    outbox.estado = OutboxCarga.Estado.PROCESADA
    outbox.procesado_en = timezone.now()
    outbox.payload = {}
    outbox.save(update_fields=["estado", "procesado_en", "payload"])
    LogAuditoria.objects.create(
        usuario=carga.usuario,
        corredor=carga.corredor,
        entidad="CargaMasiva",
        id_registro=carga.pk,
        accion=LogAuditoria.Accion.CARGA,
        valor_nuevo={
            "estado": carga.estado,
            "filas_ok": carga.filas_ok,
            "filas_error": carga.filas_error,
        },
        metodo="VALIDACION_RECHAZADA",
    )


def _cancelar_borradores_vencidos():
    ahora = timezone.now()
    with transaction.atomic():
        cargas = list(
            CargaMasiva.objects.select_for_update(
                of=("self",),
                skip_locked=True,
            )
            .filter(
                estado=CargaMasiva.Estado.PREVISUALIZADA,
                vencimiento_previsualizacion__lte=ahora,
            )
            .select_related("usuario", "corredor")
            .order_by("vencimiento_previsualizacion")[:100]
        )
        if not cargas:
            return
        ids = [carga.pk for carga in cargas]
        CargaMasiva.objects.filter(pk__in=ids).update(
            estado=CargaMasiva.Estado.CANCELADA
        )
        DetalleCarga.objects.filter(carga_id__in=ids).update(
            contenido_original={},
            datos_normalizados={},
        )
        LogAuditoria.objects.bulk_create(
            [
                LogAuditoria(
                    usuario=carga.usuario,
                    corredor=carga.corredor,
                    entidad="CargaMasiva",
                    id_registro=carga.pk,
                    accion=LogAuditoria.Accion.CARGA,
                    valor_nuevo={"estado": CargaMasiva.Estado.CANCELADA},
                    metodo="VENCIMIENTO",
                )
                for carga in cargas
            ]
        )


def procesar_siguiente_carga(cliente_mongo):
    _cancelar_borradores_vencidos()
    with transaction.atomic():
        outbox = (
            OutboxCarga.objects.select_for_update(
                of=("self",),
                skip_locked=True,
            )
            .select_related("carga", "carga__usuario", "carga__corredor")
            .filter(
                estado__in=(
                    OutboxCarga.Estado.PENDIENTE,
                    OutboxCarga.Estado.COMPENSAR,
                ),
                proximo_intento__lte=timezone.now(),
            )
            .order_by("creado_en")
            .first()
        )
        if outbox is None:
            return False

        outbox.intentos += 1
        outbox.save(update_fields=["intentos"])
        database = cliente_mongo[settings.MONGO_DB]
        collection = database["calificaciones_detalle"]
        if outbox.estado == OutboxCarga.Estado.COMPENSAR:
            try:
                _compensar(collection, outbox)
            except PyMongoError as error:
                _retrasar_compensacion(outbox)
                logger.warning(
                    "No se pudo compensar la carga %s en MongoDB: %s",
                    outbox.carga_id,
                    error,
                )
            return True

        if _hash_payload(outbox.payload) != outbox.sha256_payload:
            _programar_compensacion(outbox, "HASH_PAYLOAD_INVALIDO")
            return True
        try:
            _escribir_mongo(collection, outbox)
        except InconsistenciaMongo:
            _programar_compensacion(outbox, "INTEGRIDAD_MONGO")
            return True
        except PyMongoError as error:
            _programar_reintento(outbox, "ERROR_MONGO")
            logger.warning(
                "MongoDB no confirmó la carga %s; se reintentará: %s",
                outbox.carga_id,
                error,
            )
            return True

        if outbox.payload.get("operacion") == "VALIDACION_RECHAZOS":
            with transaction.atomic():
                _finalizar_rechazos_validacion(outbox)
            return True

        try:
            with transaction.atomic():
                _persistir_postgres(outbox)
        except (KeyError, ObjectDoesNotExist, ValueError) as error:
            logger.error(
                "La carga %s no pudo validarse al persistir: %s",
                outbox.carga_id,
                error,
            )
            _programar_compensacion(outbox, "DATOS_CARGA_INVALIDOS")
        except IntegrityError:
            if not _claves_existentes(
                _claves_payload(outbox),
                outbox.carga.usuario,
            ):
                raise
            _programar_compensacion(outbox, "CONFLICTO_LLAVE")
        return True
