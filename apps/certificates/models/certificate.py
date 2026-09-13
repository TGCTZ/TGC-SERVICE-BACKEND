"""Certificate: one per stone, the document the customer leaves with."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.gems.enums import CertificateStatus


class Certificate(BaseModel):
    """A certificate for one stone.

    The snapshot fields are deliberate denormalization, not an oversight. A
    certificate is a statement made on a date, and it has to keep saying the
    same thing afterwards: renaming a colour in the lookup table, or correcting a
    stone type, must never silently rewrite a document already in a customer's
    hands.
    """

    stone = models.OneToOneField(
        "orders.Stone", on_delete=models.PROTECT, related_name="certificate"
    )
    report = models.ForeignKey(
        "identification.IdentificationReport",
        on_delete=models.PROTECT,
        related_name="certificates",
    )
    certificate_number = models.CharField(max_length=30)

    # Frozen at issue time.
    stone_type_snapshot = models.CharField(max_length=100)
    weight_snapshot = models.DecimalField(max_digits=10, decimal_places=3)
    color_snapshot = models.CharField(max_length=100, blank=True, default="")
    origin_snapshot = models.CharField(max_length=100, blank=True, default="")
    gemmologist = models.CharField(max_length=100, blank=True, default="")

    status = models.CharField(
        max_length=20,
        choices=CertificateStatus.choices,
        default=CertificateStatus.ISSUED,
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    issued_at = models.DateTimeField()

    class Meta:
        ordering = ["-issued_at"]
        permissions = [
            ("issue_certificate", "Can issue a certificate"),
            ("revoke_certificate", "Can revoke a certificate"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["certificate_number"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_certificate_number",
            ),
        ]

    def __str__(self) -> str:
        return self.certificate_number
