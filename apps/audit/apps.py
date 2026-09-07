"""App configuration for the audit layer."""

from django.apps import AppConfig


class AuditConfig(AppConfig):
    """L2 - read-only APIs over the activity log and the application log file."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
