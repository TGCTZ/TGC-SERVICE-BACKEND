"""App configuration for the billing layer."""

from django.apps import AppConfig


class BillingConfig(AppConfig):
    """L4 - bills, payments and the GePG payment gateway."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
