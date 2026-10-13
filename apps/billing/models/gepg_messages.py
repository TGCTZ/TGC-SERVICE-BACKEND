"""Durable inbox and outbox records for GePG message delivery."""

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class GePGCallback(BaseModel):
    """A verified callback persisted before acknowledging the gateway."""

    class Kind(models.TextChoices):
        PAYMENT = "payment", "Payment notification"
        BILL = "bill", "Bill response"
        CANCELLATION = "cancellation", "Cancellation response"
        RECONCILIATION = "reconciliation", "Reconciliation response"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    event_id = models.CharField(max_length=100)
    payload = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "event_id"],
                condition=Q(deleted_at__isnull=True),
                name="billing_gepgcallback_unique_event",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="bill_gepgcb_status_created_idx",
            )
        ]


class GePGRequest(BaseModel):
    """An exact outbound GePG request, retained for idempotent retries."""

    class Operation(models.TextChoices):
        BILL = "bill", "Bill submission"
        CANCELLATION = "cancellation", "Bill cancellation"
        RECONCILIATION = "reconciliation", "Reconciliation request"

    class Status(models.TextChoices):
        SENDING = "sending", "Sending"
        RETRY = "retry", "Waiting to retry"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXHAUSTED = "exhausted", "Retries exhausted"

    operation = models.CharField(max_length=20, choices=Operation.choices)
    req_id = models.CharField(max_length=100, unique=True)
    endpoint = models.URLField(max_length=500)
    gepg_com = models.CharField(max_length=100)
    gepg_code = models.CharField(max_length=100)
    gepg_alg = models.CharField(max_length=100)
    payload = models.TextField()
    bill = models.ForeignKey(
        "billing.Bill",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gepg_requests",
    )
    cancellation = models.ForeignKey(
        "billing.BillCancellation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gepg_requests",
    )
    reconciliation = models.ForeignKey(
        "billing.Reconciliation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gepg_requests",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SENDING, db_index=True
    )
    attempts = models.PositiveIntegerField(default=0)
    first_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    response_xml = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    status_code = models.CharField(max_length=30, blank=True, default="")
    status_desc = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="bill_gepgreq_status_next_idx",
            )
        ]
