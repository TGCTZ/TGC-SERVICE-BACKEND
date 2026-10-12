"""Gateway callback routes, mounted outside the versioned API.

The paths here are registered with GePG out of band and must stay stable across
API versions - see ``webhooks.py`` for why they are not DRF views.
"""

from django.urls import path

from .webhooks import (
    BillCancelResponseView,
    BillResponseView,
    PaymentNotificationView,
    ReconciliationResponseView,
)

urlpatterns = [
    path(
        "payments/notification/",
        PaymentNotificationView.as_view(),
        name="gepg-payment-notification",
    ),
    path(
        "bill/cancel-response/",
        BillCancelResponseView.as_view(),
        name="gepg-bill-cancel-response",
    ),
    path(
        "reconciliation/response/",
        ReconciliationResponseView.as_view(),
        name="gepg-reconciliation-response",
    ),
    path(
        "bill/response/",
        BillResponseView.as_view(),
        name="gepg-bill-response",
    ),
]
