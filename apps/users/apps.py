"""App configuration for the users layer."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """L2 - custom user model, authentication and role management."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
