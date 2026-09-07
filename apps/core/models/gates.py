"""Permission-only model for coarse UI module gates.

Gates such as ``module.catalog`` decide whether a whole navigation section is
visible. They guard no table of their own, so they are declared on an unmanaged
model that exists purely to hang permissions off. Django still creates rows in
``auth_permission`` for unmanaged models, which is what makes this work.
"""

from django.db import models


class ModuleGate(models.Model):
    """No table, no rows - only the permissions declared in ``Meta``."""

    class Meta:
        managed = False  # no migration creates a table for this
        default_permissions = ()  # suppress add/change/delete/view
        permissions = [
            ("module_user", "Can access the user module"),
            ("module_catalog", "Can access the catalog module"),
            ("module_settings", "Can access the settings module"),
            ("module_audit", "Can access the audit module"),
        ]
