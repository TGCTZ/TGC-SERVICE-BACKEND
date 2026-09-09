"""Gateway callback routes, mounted outside the versioned API.

The paths here are registered with GePG out of band and must stay stable across
API versions - see ``webhooks.py`` for why they are not DRF views.
"""

from django.urls import path

from .webhooks import BillResponseView, PaymentNotificationView

urlpatterns = [
    path(
        "payments/notification/",
        PaymentNotificationView.as_view(),
        name="gepg-payment-notification",
    ),
    path(
        "bill/response/",
        BillResponseView.as_view(),
        name="gepg-bill-response",
    ),
]
