"""Rendering a certificate to PDF.

WeasyPrint takes HTML + CSS and returns PDF bytes - no headless browser, and the
document stays editable by anyone who can read a template. The cost is system
libraries (pango, cairo, gdk-pixbuf); a missing one raises ``OSError`` at import
time, so it takes the whole app down rather than just this endpoint. See
``backend/README.md`` for the package list.

The layout is a port of the document the lab already issues: A4 landscape, three
columns, one page. It is driven entirely from the certificate's own snapshot
columns - never from the live report - so a document reproduced years later says
exactly what it said on the day it was issued.
"""

from weasyprint import HTML

from django.conf import settings
from django.template.loader import render_to_string

from apps.gems.enums import CertificateStatus, WeightUnit

from ..models import Certificate
from .assets import lab_assets, photo_data_uri, qr_data_uri, verification_url

TEMPLATE = "certificates/certificate.html"


def certificate_context(certificate: Certificate) -> dict:
    """Build the template context for one certificate.

    Split out from the render so tests can assert on what the document *says*
    without parsing PDF bytes - which is the only way to check the snapshot
    guarantee (that renaming a colour afterwards does not rewrite the document).

    Every finding comes from a ``*_snapshot`` column. The report and stone are
    reached only for things that are not statements about the findings: the
    stone's label, the order it came in on, and the customer.

    Args:
        certificate: The certificate to describe.

    Returns:
        The template context: lab identity, the frozen findings, the lab's
        marks and the verification QR.
    """
    stone = certificate.stone
    order = stone.order
    verify_url = verification_url(certificate.certificate_number)

    return {
        "certificate": certificate,
        "weight_unit": WeightUnit(certificate.weight_unit_snapshot).symbol,
        "is_revoked": certificate.status == CertificateStatus.REVOKED,
        "ministry_name": settings.CERTIFICATE_MINISTRY_NAME,
        "lab_name": settings.CERTIFICATE_LAB_NAME,
        "lab_address": settings.CERTIFICATE_LAB_ADDRESS,
        "stone_label": stone.label,
        "order_reference": order.reference_number,
        "customer_name": order.customer.full_name,
        # The number printed as REPORT NO. Snapshotted, falling back to the live
        # report only for certificates issued before snapshotting existed.
        "report_number": (
            certificate.report_number_snapshot or certificate.report.report_number
        ),
        "instruments": certificate.instruments_snapshot or [],
        "photo": photo_data_uri(certificate.photo_snapshot) or photo_data_uri(stone.photo),
        "verify_url": verify_url,
        "qr_code": qr_data_uri(verify_url),
        **lab_assets(),
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
    # No base_url: every image in the document is an inline data: URI, so there
    # is nothing left to resolve against the filesystem. See services/assets.py.
    return HTML(string=html).write_pdf()
