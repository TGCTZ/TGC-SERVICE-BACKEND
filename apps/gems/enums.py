"""Every enum the TGC domain uses.

They live together at L2, below the apps that own the corresponding tables,
because several of them are read across app boundaries: the findings worklist in
``identification`` filters on ``BillStatus.PAID``, and the certification worklist
does the same. Keeping the enums here lets those apps sit at the same layer
without importing one another - the join itself (``order__bill__status``) is a
plain ORM traversal that needs no import.
"""

from django.db import models


class StoneStatus(models.TextChoices):
    """Per-stone lifecycle stages.

    Only ``received``, ``billed``, ``paid`` and ``certified`` are written by any
    code path today; the rest describe stages of the documented workflow that
    have no implementation yet. They are kept so a client can render a stone
    whose status was set by hand, and so the intended lifecycle stays visible.
    """

    RECEIVED = ("received", "Received")
    UNDER_IDENTIFICATION = ("under_identification", "Under identification")
    BILLED = ("billed", "Billed")
    PAID = ("paid", "Paid")
    CERTIFIED = ("certified", "Certified")
    READY_FOR_COLLECTION = ("ready_for_collection", "Ready for collection")
    COLLECTED = ("collected", "Collected")
    ON_HOLD = ("on_hold", "On hold")
    CANCELLED = ("cancelled", "Cancelled")


class StoneCategory(models.TextChoices):
    """Stone classification; drives pricing tiers."""

    PRECIOUS = ("precious", "Precious")
    SEMI_PRECIOUS = ("semi_precious", "Semi-precious")
    DIAMOND = ("diamond", "Diamond")


class ColorGroup(models.TextChoices):
    """Broad color families used to group the color lookup (GIA-style)."""

    WHITE_GREY_BLACK = ("white_grey_black", "White/Grey/Black")
    PURPLE_VIOLET = ("purple_violet", "Purple/Violet")
    RED_PINK = ("red_pink", "Red/Pink")
    ORANGE_YELLOW = ("orange_yellow", "Orange/Yellow")
    GREEN = ("green", "Green")
    BLUE = ("blue", "Blue")


class WeightUnit(models.TextChoices):
    """Unit for stone weight."""

    CARAT = ("carat", "Carat")
    GRAM = ("gram", "Gram")

    @property
    def symbol(self) -> str:
        """Short display symbol, e.g. 'ct' or 'g'."""
        return {self.CARAT: "ct", self.GRAM: "g"}[self]


class Transparency(models.TextChoices):
    """How light passes through the stone."""

    TRANSPARENT = ("transparent", "Transparent")
    TRANSLUCENT = ("translucent", "Translucent")
    OPAQUE = ("opaque", "Opaque")


class NatureType(models.TextChoices):
    """Whether the stone is natural or man-made/altered."""

    NATURAL = ("natural", "Natural")
    SYNTHETIC = ("synthetic", "Synthetic")
    TREATED = ("treated", "Treated")
    ENHANCED = ("enhanced", "Enhanced")
    ARTIFICIAL = ("artificial", "Artificial")


class Treatment(models.TextChoices):
    """Enhancement applied to the stone, if any."""

    NONE = ("none", "None")
    HEATED = ("heated", "Heated")
    OILED = ("oiled", "Oiled")
    DYED = ("dyed", "Dyed")
    IRRADIATED = ("irradiated", "Irradiated")
    FRACTURE_FILLED = ("fracture_filled", "Fracture filled")
    BLEACHED = ("bleached", "Bleached")
    IMPREGNATED = ("impregnated", "Impregnated")


class OpticCharacter(models.TextChoices):
    """Optical behavior under polarized light.

    The stored value is the lowercase code; the label carries the expansion the
    report prints.
    """

    SR = ("sr", "SR - Singly refractive")
    ADR = ("adr", "ADR - Anomalous double refractive")
    DR = ("dr", "DR - Double refractive")
    AGG = ("agg", "AGG - Aggregate")


class BillStatus(models.TextChoices):
    """Payment state of a bill.

    ``cancelled`` and ``expired`` have no code path yet: ``Bill.expiry_at`` is
    recorded but nothing acts on it, and bill cancellation against the gateway is
    not implemented.
    """

    PENDING = ("pending", "Pending")
    PARTIALLY_PAID = ("partially_paid", "Partially paid")
    PAID = ("paid", "Paid")
    CANCELLED = ("cancelled", "Cancelled")
    EXPIRED = ("expired", "Expired")


class CertificateStatus(models.TextChoices):
    """Validity state of a certificate.

    ``reissued`` is unreachable; there is no re-issue service.
    """

    ISSUED = ("issued", "Issued")
    REVOKED = ("revoked", "Revoked")
    REISSUED = ("reissued", "Reissued")
