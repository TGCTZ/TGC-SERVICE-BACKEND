"""Root URL configuration.

Application endpoints live under ``/api/v1/``. Schema and documentation sit
outside the version prefix so tooling can find them at stable paths, and so do
the GePG gateway callbacks under ``/gepg/`` - their URLs are registered with the
gateway and must survive an API version bump.
"""

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.gems.urls")),
    path("api/v1/", include("apps.orders.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.identification.urls")),
    path("api/v1/", include("apps.certificates.urls")),
    path("api/v1/", include("apps.audit.urls")),
    # Gateway callbacks: server-to-server XML, registered with GePG out of band,
    # so deliberately outside the versioned API. See apps/billing/webhooks.py.
    path("gepg/", include("apps.billing.urls_webhooks")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
