"""Reporting periods: the dates a statistic covers and how they are bucketed.

Every section of the management statistics answers "how much, per what?" over
a range the caller picks. This module owns that arithmetic so each selector
only has to say *what* it counts:

- A range is inclusive dates on the lab's own calendar (``LAB_TIME_ZONE``),
  not UTC. The server stores UTC, and a payment made at 22:00 in Dar es Salaam
  belongs to the next UTC day but to *this* day at the lab.
- The bucket size follows the length of the range - days for a month, weeks
  for up to half a year, months beyond - so a chart never has three bars or
  three hundred.
- Series are zero-filled, so a quiet week is a zero on the axis rather than a
  gap the chart silently draws a line across.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models.functions import TruncDate

DAY = "day"
WEEK = "week"
MONTH = "month"

#: Longest range accepted. Beyond this a "trend" is history, and the rows
#: fetched for the in-Python statistics stop being cheap.
MAX_DAYS = 3 * 366


def lab_tz() -> ZoneInfo:
    """The zone the lab's calendar days are counted in."""
    return ZoneInfo(settings.LAB_TIME_ZONE)


def local_date(moment: datetime) -> date:
    """The lab-calendar day an aware datetime falls on."""
    return moment.astimezone(lab_tz()).date()


def lab_day(field: str) -> TruncDate:
    """An ORM expression for the lab-calendar day of a datetime column."""
    return TruncDate(field, tzinfo=lab_tz())


def months_back(day: date, months: int) -> date:
    """The first of the month ``months`` before ``day``'s month."""
    index = day.year * 12 + (day.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


@dataclass(frozen=True)
class Period:
    """An inclusive range of lab-calendar days.

    Attributes:
        start: First day counted.
        end: Last day counted.
    """

    start: date
    end: date

    @classmethod
    def default(cls, today: date) -> "Period":
        """The last twelve calendar months, this one included.

        Whole months rather than "365 days ago", so a monthly chart opens on a
        full first bar instead of a sliver of one.
        """
        return cls(months_back(today, 11), today)

    @property
    def days(self) -> int:
        """How many days the range covers."""
        return (self.end - self.start).days + 1

    @property
    def granularity(self) -> str:
        """The bucket size a chart over this range should use."""
        if self.days <= 31:
            return DAY
        if self.days <= 26 * 7:
            return WEEK
        return MONTH

    def previous(self) -> "Period":
        """The equally long range that ends the day before this one starts.

        What a KPI is compared against: "up 12% on the previous 30 days" only
        means something if both sides count the same number of days.
        """
        end = self.start - timedelta(days=1)
        return Period(end - timedelta(days=self.days - 1), end)

    def bounds(self) -> tuple[datetime, datetime]:
        """Aware ``[start, end)`` datetimes covering the range at the lab."""
        tz = lab_tz()
        return (
            datetime.combine(self.start, time.min, tz),
            datetime.combine(self.end + timedelta(days=1), time.min, tz),
        )

    def bucket(self, day: date) -> date:
        """The first day of the bucket ``day`` belongs to.

        Weeks start on Monday (ISO 8601), months on the 1st. A bucket may begin
        before :attr:`start`; it is labelled by its own first day regardless.
        """
        if self.granularity == DAY:
            return day
        if self.granularity == WEEK:
            return day - timedelta(days=day.weekday())
        return day.replace(day=1)

    def buckets(self) -> list[date]:
        """Every bucket the range touches, in order."""
        result = []
        current = self.bucket(self.start)
        while current <= self.end:
            result.append(current)
            if self.granularity == DAY:
                current += timedelta(days=1)
            elif self.granularity == WEEK:
                current += timedelta(weeks=1)
            else:
                current = months_back(current, -1)
        return result

    def rollup(self, daily: Iterable[tuple[date, float]]) -> dict[date, float]:
        """Add per-day values into this range's buckets, zero-filled.

        Args:
            daily: ``(day, value)`` pairs, typically one per day from the
                database. Days outside the range are ignored.
        """
        totals: dict[date, float] = dict.fromkeys(self.buckets(), 0)
        for day, value in daily:
            if day is not None and self.start <= day <= self.end:
                totals[self.bucket(day)] += value or 0
        return totals

    def as_dict(self) -> dict:
        """The range as the API reports it."""
        return {
            "from": self.start.isoformat(),
            "to": self.end.isoformat(),
            "granularity": self.granularity,
        }
