"""Configuration package; expose the Celery app for worker discovery."""

from .celery import app as celery_app

__all__ = ("celery_app",)
