"""App configuration for the identification layer."""

from django.apps import AppConfig


class IdentificationConfig(AppConfig):
    """L4 - gemmological findings recorded against a stone."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.identification"
