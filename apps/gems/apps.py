"""App configuration for the gemmological reference layer."""

from django.apps import AppConfig


class GemsConfig(AppConfig):
    """L2 - domain enums and the stone reference tables."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gems"
