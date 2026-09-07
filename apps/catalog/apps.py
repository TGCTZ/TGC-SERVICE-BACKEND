"""App configuration for the catalog layer."""

from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """L3 - the product domain and its lookup tables."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
