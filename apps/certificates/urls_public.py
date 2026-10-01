"""Public certificate routes, mounted outside the versioned API.

The path here is printed on physical certificates and registered nowhere else,
so it must stay stable across API versions - see ``verify.py`` for why this is
not a DRF view.
"""

from django.urls import path

from .verify import CertificateVerifyView

urlpatterns = [
    path(
        "<str:certificate_number>/",
        CertificateVerifyView.as_view(),
        name="certificate-verify",
    ),
]
