"""Permission carrier for the audit app.

Change history itself lives in ``auditlog.LogEntry``, and the system log is a
file on disk, so this app owns no data. The model below exists only so Django
creates a permission that the system-log endpoint can check.
"""

from django.db import models


class SystemLogAccess(models.Model):
    """No table, no rows - only the permission declared in ``Meta``."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [("view_systemlog", "Can read the application log file")]
