"""Reporting sits above the domain apps it reads."""

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """L6 - read-only financial and operational reports."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"
