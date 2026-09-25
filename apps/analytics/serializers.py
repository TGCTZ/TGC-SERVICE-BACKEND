"""Query-parameter validation for the statistics endpoints."""

from rest_framework import serializers

from django.utils import timezone

from .periods import MAX_DAYS, Period, local_date


class PeriodQuerySerializer(serializers.Serializer):
    """``?from=YYYY-MM-DD&to=YYYY-MM-DD`` - both optional, both inclusive.

    Validates to a :class:`~apps.analytics.periods.Period`. Without ``to`` the
    range ends today on the lab's calendar; without ``from`` it covers the
    twelve calendar months ending at ``to``.
    """

    def get_fields(self):
        """Declare the fields here: ``from`` is a keyword, so no class attribute."""
        return {
            "from": serializers.DateField(required=False),
            "to": serializers.DateField(required=False),
        }

    def validate(self, attrs):
        """Fill in the defaults and refuse ranges that are backwards or too long."""
        end = attrs.get("to") or local_date(timezone.now())
        start = attrs.get("from") or Period.default(end).start
        if start > end:
            raise serializers.ValidationError({"from": "Must be on or before `to`."})

        period = Period(start, end)
        if period.days > MAX_DAYS:
            raise serializers.ValidationError(
                {"from": f"A range can cover at most {MAX_DAYS} days."}
            )
        return period
