from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.cuentas.views import (
    CambiarClaveView,
    CsrfTokenView,
    PerfilActualView,
    TokenLoginView,
    TokenLogoutView,
    TokenRefreshView,
)
from apps.cuentas.admin_api import (
    RestablecerClaveTemporalView,
    UsuarioAdminDetalleView,
    UsuariosAdminView,
)
from apps.calificaciones.api_views import CatalogosView
from apps.calificaciones.catalogos_admin_api import ColumnaTributariaAdminView
from apps.calificaciones.auditoria_api import AuditoriaView
from apps.calificaciones.cargas_api import (
    CargaMasivaEstadoView,
    CargaMasivaPlantillaView,
    CargaMasivaPrevisualizarView,
)
from apps.calificaciones.views import CalificacionViewSet


def health(request):
    return JsonResponse({"estado": "disponible", "servicio": "nuam-api"})


router = DefaultRouter()
router.register(
    "calificaciones",
    CalificacionViewSet,
    basename="calificacion",
)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/salud/", health, name="salud"),
    path("api/v1/auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("api/v1/auth/login/", TokenLoginView.as_view(), name="auth-login"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("api/v1/auth/logout/", TokenLogoutView.as_view(), name="auth-logout"),
    path("api/v1/auth/me/", PerfilActualView.as_view(), name="auth-me"),
    path(
        "api/v1/auth/cambiar-clave/",
        CambiarClaveView.as_view(),
        name="auth-cambiar-clave",
    ),
    path("api/v1/usuarios/", UsuariosAdminView.as_view(), name="usuarios-admin"),
    path(
        "api/v1/usuarios/<int:pk>/",
        UsuarioAdminDetalleView.as_view(),
        name="usuario-admin-detalle",
    ),
    path(
        "api/v1/usuarios/<int:pk>/clave-temporal/",
        RestablecerClaveTemporalView.as_view(),
        name="usuario-admin-clave-temporal",
    ),
    path("api/v1/catalogos/", CatalogosView.as_view(), name="catalogos"),
    path(
        "api/v1/catalogos/columnas/<int:pk>/",
        ColumnaTributariaAdminView.as_view(),
        name="catalogo-columna-admin",
    ),
    path("api/v1/auditoria/", AuditoriaView.as_view(), name="auditoria"),
    path(
        "api/v1/cargas/plantilla/",
        CargaMasivaPlantillaView.as_view(),
        name="carga-plantilla",
    ),
    path(
        "api/v1/cargas/previsualizar/",
        CargaMasivaPrevisualizarView.as_view(),
        name="carga-previsualizar",
    ),
    path(
        "api/v1/cargas/",
        CargaMasivaEstadoView.as_view(),
        name="cargas-lista",
    ),
    path(
        "api/v1/cargas/<int:pk>/",
        CargaMasivaEstadoView.as_view(),
        name="carga-estado",
    ),
    path(
        "api/v1/cargas/<int:pk>/confirmar/",
        CargaMasivaEstadoView.as_view(),
        name="carga-confirmar",
    ),
    path("api/v1/", include(router.urls)),
]
