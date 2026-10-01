"""App configuration for the order-intake layer."""

from django.apps import AppConfig


class OrdersConfig(AppConfig):
    """L3 - customers, orders and the stones they contain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orders"
