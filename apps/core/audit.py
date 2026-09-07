"""Register models with django-auditlog for change-history tracking."""

from auditlog.registry import auditlog

from django.apps import apps
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

# Columns auditlog or BaseModel already capture out of band. Keeping them out of
# the diff stops every row from reporting a meaningless updated_at change.
# deleted_at stays tracked so soft deletes still surface as changes.
EXCLUDED_FIELDS = [
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "deleted_by",
]


def register_audit_models():
    """Register every concrete ``BaseModel`` subclass, plus the user model.

    Discovery by base class means a new model is audited the moment it inherits
    ``BaseModel`` - there is no per-model registration list to forget to update.
    """
    for model in apps.get_models():
        if issubclass(model, BaseModel) and not model._meta.abstract:
            auditlog.register(model, exclude_fields=EXCLUDED_FIELDS)
    auditlog.register(get_user_model(), exclude_fields=["password", "last_login"])
