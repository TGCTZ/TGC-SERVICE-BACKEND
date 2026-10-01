"""App configuration for the in-app notification layer."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """L2 - per-user notifications raised by the pipeline's station handoffs."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
