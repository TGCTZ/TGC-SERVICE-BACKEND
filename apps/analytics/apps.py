"""App configuration for the management statistics."""

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """L6 - read-only aggregates over every other app, for the management team."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
