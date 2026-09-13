"""Rendering a certificate to PDF.

WeasyPrint takes HTML + CSS and returns PDF bytes - no headless browser, and the
document stays editable by anyone who can read a template. The cost is system
libraries (pango, cairo, gdk-pixbuf); a missing one raises ``OSError`` at import
time, so it takes the whole app down rather than just this endpoint. See
``backend/README.md`` for the package list.
"""

from weasyprint import HTML

from django.conf import settings
from django.template.loader import render_to_string

from apps.gems.enums import CertificateStatus

from ..models import Certificate

TEMPLATE = "certificates/certificate.html"


def certificate_context(certificate: Certificate) -> dict:
    """Build the template context for one certificate.

    Split out from the render so tests can assert on what the document *says*
    without parsing PDF bytes - which is the only way to check the snapshot
    guarantee (that renaming a colour afterwards does not rewrite the document).

    Args:
        certificate: The certificate to describe.

    Returns:
        The template context: lab identity, the certificate, and its provenance.
    """
    stone = certificate.stone
    order = stone.order

    return {
        "certificate": certificate,
        "is_revoked": certificate.status == CertificateStatus.REVOKED,
        "lab_name": settings.CERTIFICATE_LAB_NAME,
        "lab_address": settings.CERTIFICATE_LAB_ADDRESS,
        "stone_label": stone.label,
        "order_reference": order.reference_number,
        "customer_name": order.customer.full_name,
        "report_number": certificate.report.report_number,
    }


def render_certificate_pdf(certificate: Certificate) -> bytes:
    """Render a certificate to PDF bytes, ready to stream or save.

    Args:
        certificate: The certificate to render.

    Returns:
        The PDF as bytes. A revoked certificate still renders, carrying a
        REVOKED watermark - refusing would leave staff unable to reconcile
        paperwork, and the watermark carries the meaning.
    """
    html = render_to_string(TEMPLATE, certificate_context(certificate))
    return HTML(string=html).write_pdf()
