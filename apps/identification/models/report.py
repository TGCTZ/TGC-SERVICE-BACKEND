"""Identification report (one per stone) and the instruments used on it."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.gems.enums import NatureType, OpticCharacter, Transparency, Treatment


class IdentificationReport(BaseModel):
    """A gemmologist's findings for a single stone.

    Every finding is optional: a report is built up over a sitting at the bench,
    and a stone may defeat one test while answering another. What makes it
    authoritative is ``is_finalized``, which is one-way.

    **One live report per stone**, enforced by a conditional unique constraint
    rather than by ``OneToOneField``. A OneToOne is a plain unique index on
    ``stone_id``, which the database applies to soft-deleted rows too - so a
    discarded report went on occupying its stone's slot forever, and the stone
    could never be reported on again. The relation is a ForeignKey carrying a
    ``deleted_at IS NULL`` constraint instead, which is the same rule the
    ``report_number`` constraint already uses. Read the live one through
    :attr:`orders.Stone.report`.
    """

    stone = models.ForeignKey(
        "orders.Stone", on_delete=models.CASCADE, related_name="reports"
    )
    report_number = models.CharField(max_length=50)

    # Reference-table attributes. PROTECT everywhere except colour: a lookup that
    # a report cites must not vanish underneath it.
    species = models.ForeignKey(
        "gems.Species",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    variety = models.ForeignKey(
        "gems.Variety",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    origin = models.ForeignKey(
        "gems.Origin", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    shape_cut = models.ForeignKey(
        "gems.ShapeCut",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    color = models.ForeignKey(
        "gems.Color", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Fixed-value attributes.
    nature_type = models.CharField(
        max_length=20, choices=NatureType.choices, blank=True, default=""
    )
    transparency = models.CharField(
        max_length=20, choices=Transparency.choices, blank=True, default=""
    )
    treatment = models.CharField(
        max_length=20, choices=Treatment.choices, blank=True, default=""
    )
    optic_character = models.CharField(
        max_length=20, choices=OpticCharacter.choices, blank=True, default=""
    )

    # Measurements.
    dimensions = models.CharField(max_length=50, blank=True, default="")
    refractive_index = models.CharField(max_length=50, blank=True, default="")
    specific_gravity = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    is_polished = models.BooleanField(default=False)
    conclusion = models.TextField(blank=True, default="")

    # Workflow.
    is_finalized = models.BooleanField(default=False)
    identified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    identified_at = models.DateTimeField(null=True, blank=True)
    # The second gemmologist, named on the certificate beside the first.
    #
    # The printed report claims it was "examined by at least two qualified
    # Gemmologists", so the claim needs somebody standing behind it. Nullable
    # because a report can be drafted before the second opinion exists;
    # `finalize_report` is where it is asked for. PROTECT rather than SET_NULL:
    # unlike `identified_by` this name is a signature, and a certificate must
    # not quietly lose one of the two people who signed it.
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reports_verified",
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [("finalize_report", "Can finalize an identification report")]
        constraints = [
            models.UniqueConstraint(
                fields=["report_number"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_report_number",
            ),
            # One *live* report per stone. Discarding a report frees the stone
            # to be reported on again, which is what the delete dialog promises.
            models.UniqueConstraint(
                fields=["stone"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_live_stone",
            ),
        ]

    def __str__(self) -> str:
        return self.report_number


class InstrumentUsed(BaseModel):
    """An instrument used during a report, with its reading."""

    report = models.ForeignKey(
        IdentificationReport, on_delete=models.CASCADE, related_name="instruments_used"
    )
    instrument = models.ForeignKey(
        "gems.Instrument", on_delete=models.PROTECT, related_name="+"
    )
    reading = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ["report", "id"]

    def __str__(self) -> str:
        return (
            f"{self.instrument} ({self.reading})"
            if self.reading
            else str(self.instrument)
        )
