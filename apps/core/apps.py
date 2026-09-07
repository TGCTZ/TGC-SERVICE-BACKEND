"""App configuration for the core layer."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """L1 - base models, managers and shared DRF machinery."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        """Register every auditable model once the app registry is populated."""
        from apps.core.audit import register_audit_models

        register_audit_models()
