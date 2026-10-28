import hashlib
import json

from django.db.models import Q

from .models import Calificacion


def _hash_payload(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _claves_existentes(claves, perfil):
    if not claves:
        return set()
    existentes = set()
    claves_unicas = list(set(claves))
    for inicio in range(0, len(claves_unicas), 100):
        grupo = claves_unicas[inicio:inicio + 100]
        filtro = Q()
        for instrumento_id, ejercicio, fecha_pago, secuencia in grupo:
            filtro |= Q(
                instrumento_id=instrumento_id,
                ejercicio=ejercicio,
                fecha_pago=fecha_pago,
                secuencia_evento=secuencia,
            )
        queryset = Calificacion.objects.filter(
            filtro,
            estado=Calificacion.Estado.VIGENTE,
        )
        if perfil.corredor_id:
            queryset = queryset.filter(corredor_id=perfil.corredor_id)
        else:
            queryset = queryset.filter(corredor__isnull=True)
        existentes.update(
            queryset.values_list(
                "instrumento_id",
                "ejercicio",
                "fecha_pago",
                "secuencia_evento",
            )
        )
    return existentes
