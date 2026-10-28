from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cuentas.permissions import SoloAuditoriaPermission

from .models import LogAuditoria


class AuditoriaView(APIView):
    permission_classes = [IsAuthenticated, SoloAuditoriaPermission]
    page_size_max = 100

    def get(self, request):
        parametros = request.query_params
        try:
            pagina = int(parametros.get("pagina", "1"))
            limite = int(parametros.get("limite", "25"))
        except ValueError:
            return Response(
                {
                    "detalle": (
                        "La página y el límite deben ser números enteros."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pagina < 1 or not 1 <= limite <= self.page_size_max:
            return Response(
                {
                    "detalle": (
                        "La página debe ser positiva y el límite estar entre 1 y 100."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = LogAuditoria.objects.select_related("usuario", "corredor")
        accion = parametros.get("accion")
        acciones_validas = {valor for valor, _ in LogAuditoria.Accion.choices}
        if accion:
            if accion not in acciones_validas:
                return Response(
                    {"accion": "Selecciona una acción de auditoría válida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(accion=accion)

        for nombre, lookup in (
            ("desde", "fecha_hora__date__gte"),
            ("hasta", "fecha_hora__date__lte"),
        ):
            valor = parametros.get(nombre)
            if valor:
                fecha = parse_date(valor)
                if fecha is None:
                    return Response(
                        {nombre: "Usa una fecha válida con formato AAAA-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                queryset = queryset.filter(**{lookup: fecha})

        corredor = parametros.get("corredor")
        if corredor:
            if not corredor.isdecimal():
                return Response(
                    {"corredor": "El identificador del corredor debe ser numérico."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(corredor_id=int(corredor))

        total = queryset.count()
        inicio = (pagina - 1) * limite
        eventos = queryset[inicio:inicio + limite]
        return Response(
            {
                "total": total,
                "pagina": pagina,
                "limite": limite,
                "resultados": [
                    {
                        "id": evento.pk,
                        "fecha_hora": evento.fecha_hora,
                        "usuario": evento.usuario.email,
                        "corredor": (
                            evento.corredor.nombre if evento.corredor_id else None
                        ),
                        "entidad": evento.entidad,
                        "id_registro": evento.id_registro,
                        "accion": evento.accion,
                        "metodo": evento.metodo,
                        "valor_anterior": evento.valor_anterior,
                        "valor_nuevo": evento.valor_nuevo,
                    }
                    for evento in eventos
                ],
            }
        )
