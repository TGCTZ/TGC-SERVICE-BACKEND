"""Reads that encode a certification workflow gate."""

from apps.gems.enums import BillStatus
from apps.orders.models import Stone

from .models import Certificate


def certification_worklist():
    """Stones ready to be certified.

    Findings signed off, bill settled, no certificate yet - the three issuance
    guards expressed as a queue, so the screen and the service agree.
    """
    return Stone.objects.select_related(
        "order", "order__customer", "stone_type", "report"
    ).filter(
        report__is_finalized=True,
        order__bill__status=BillStatus.PAID,
        certificate__isnull=True,
    )


def certificate_by_token(token: str) -> Certificate | None:
    """Resolve a certificate from its public verification token.

    Returns None rather than raising: an unknown token is an ordinary answer for
    a public endpoint ("no such certificate"), not an error.
    """
    return (
        Certificate.objects.select_related(
            "stone", "stone__order", "stone__order__customer", "report"
        )
        .filter(verification_token=token)
        .first()
    )
