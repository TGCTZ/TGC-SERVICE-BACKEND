"""In-app notifications for staff users."""

from django.conf import settings
from django.db import models


class NotificationKind(models.TextChoices):
    """The station handoffs that raise a notification.

    Each kind is a point where the pipeline waits on someone to act. The stored
    values are read by the frontend (icons, grouping), so never rename one once
    rows exist - add a new member instead.
    """

    ORDER_RECEIVED = ("order_received", "Order received")
    READY_TO_BILL = ("ready_to_bill", "Ready to bill")
    BILL_PAID = ("bill_paid", "Bill paid")
    READY_TO_CERTIFY = ("ready_to_certify", "Ready to certify")
    READY_FOR_COLLECTION = ("ready_for_collection", "Ready for collection")


def subscription_codename(kind: str) -> str:
    """The permission codename that subscribes a user to one kind."""
    return f"receive_{NotificationKind(kind).value}"


class Notification(models.Model):
    """One message for one recipient.

    Deliberately a plain ``models.Model`` rather than a ``BaseModel``:
    notifications are high-volume and disposable, so soft-delete and audit
    columns would only add weight. They are fanned out one row per recipient so
    read state is per person and the inbox query is a single indexed lookup.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=40, choices=NotificationKind.choices)
    title = models.CharField(max_length=150)
    body = models.TextField(blank=True, default="")
    # A frontend route, not an absolute URL, so it survives a domain change.
    link = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    # Null means unread; a timestamp rather than a flag keeps "when" for free.
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        # The model's add/change/delete/view permissions are dropped: the inbox
        # is scoped to its owner and checks none of them, so in the roles matrix
        # they would be switches wired to nothing.
        default_permissions = ()
        # Opt-in subscriptions, one per kind, granted to the desk the work waits
        # on (see apps.users.roles). Deliberately not the action's own
        # permission: manager and superadmin hold every action so they can step
        # in, but a handoff to someone who will not act on it is noise.
        permissions = [
            (subscription_codename(kind), f"Receive '{kind.label}' notifications")
            for kind in NotificationKind
        ]
        # Serves the inbox and unread-count queries: filter by recipient, then
        # unread, newest first.
        indexes = [models.Index(fields=["recipient", "read_at", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.recipient}: {self.title}"

    @property
    def is_read(self) -> bool:
        """Whether the recipient has read this notification."""
        return self.read_at is not None
