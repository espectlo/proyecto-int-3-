from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cuentas.permissions import PerfilSinCambioClavePermission

from .models import ColumnaTributaria, Instrumento, Mercado, OrigenInformacion


class CatalogosView(APIView):
    permission_classes = [IsAuthenticated, PerfilSinCambioClavePermission]

    def get(self, request):
        mercados = Mercado.objects.filter(activo=True).values("id", "codigo", "nombre")
        parametros = request.query_params
        instrumentos = Instrumento.objects.filter(activo=True).select_related(
            "mercado"
        )
        if parametros.get("mercado"):
            instrumentos = instrumentos.filter(
                mercado__codigo=parametros["mercado"]
            )
        return Response(
            {
                "mercados": list(mercados),
                "instrumentos": [
                    {
                        "id": instrumento.pk,
                        "codigo": instrumento.codigo,
                        "nombre": instrumento.nombre,
                        "mercado": instrumento.mercado.codigo,
                        "mercado_nombre": instrumento.mercado.nombre,
                        "inscrito": instrumento.inscrito,
                    }
                    for instrumento in instrumentos
                ],
                "origenes": list(
                    OrigenInformacion.objects.values("codigo", "descripcion")
                ),
                "columnas_tributarias": list(
                    ColumnaTributaria.objects.filter(activa=True)
                    .order_by("nro_columna")
                    .values(
                        "nro_columna",
                        "nombre_homologado",
                        "tipo_dato",
                        "formula",
                        "pendiente_homologacion",
                        "reglas_provisionales",
                    )
                ),
            }
        )
