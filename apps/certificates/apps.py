"""App configuration for the certification layer."""

from django.apps import AppConfig


class CertificatesConfig(AppConfig):
    """L5 - the certificate a stone leaves with, and its public verification."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.certificates"
