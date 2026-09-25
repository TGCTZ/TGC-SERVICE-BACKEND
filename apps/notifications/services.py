"""Raising in-app notifications.

The single entry point every app calls. Channels beyond the in-app inbox (SMS is
planned) belong behind these functions, so a caller never learns how a message
travels.
"""

from django.contrib.auth.backends import ModelBackend
from django.db import transaction

from .models import Notification, subscription_codename


def notify(*, kind: str, recipients, title: str, body: str = "", link: str = "") -> None:
    """Send one notification to each recipient once the transaction commits.

    Deferred to commit because the event may still roll back: a notification
    about an order that was never saved would send someone to a record that
    does not exist. ``robust`` because the business action has already
    committed by then - a failed notification is logged, never surfaced as an
    error on a request that actually succeeded.

    Args:
        kind: A ``NotificationKind`` value.
        recipients: Users, or a lazy queryset of them; evaluated at commit.
        title: The one-line summary the bell shows.
        body: Optional detail.
        link: A frontend route to open when the notification is clicked.
    """

    def deliver():
        Notification.objects.bulk_create(
            Notification(
                recipient_id=recipient_id,
                kind=kind,
                title=title[:150],
                body=body,
                link=link,
            )
            for recipient_id in {user.pk for user in recipients}
        )

    transaction.on_commit(deliver, robust=True)


def notify_subscribers(
    kind: str,
    *,
    title: str,
    body: str = "",
    link: str = "",
    exclude=None,
) -> None:
    """Notify every active user subscribed to ``kind``.

    Subscribed means holding ``notifications.receive_<kind>``, which
    ``apps.users.roles`` grants to the one desk each handoff is for. Resolved by
    permission rather than role name, so a user in two roles hears through
    either, and an administrator can re-route a handoff from the roles screen
    without a deploy. Superuser *flags* are ignored for the same reason
    superadmin is denied these permissions: the break-glass account is not a
    desk.

    Args:
        kind: A ``NotificationKind`` value; also picks the subscription.
        title: The one-line summary the bell shows.
        body: Optional detail.
        link: A frontend route to open when the notification is clicked.
        exclude: The acting user, who already knows what they just did.
    """
    perm = f"notifications.{subscription_codename(kind)}"
    recipients = ModelBackend().with_perm(perm, is_active=True, include_superusers=False)
    if exclude is not None:
        recipients = recipients.exclude(pk=exclude.pk)
    notify(
        kind=kind,
        recipients=recipients.only("pk"),
        title=title,
        body=body,
        link=link,
    )
