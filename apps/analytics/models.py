"""Permission carrier for the management statistics.

The statistics are aggregates over tables other apps own, so this app has no
data of its own. The model below exists only so Django creates the permission
the statistics endpoints check - the same arrangement as ``audit``.
"""

from django.db import models


class StatisticsAccess(models.Model):
    """No table, no rows - only the permission declared in ``Meta``."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [("view_statistics", "Can view management statistics")]
