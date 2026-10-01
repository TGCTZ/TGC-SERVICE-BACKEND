"""Read-only endpoints behind the Management tab of the dashboard."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from . import selectors
from .permissions import CanViewStatistics
from .serializers import PeriodQuerySerializer

PERIOD_PARAMETERS = [
    OpenApiParameter(
        "from",
        OpenApiTypes.DATE,
        description="First day counted, inclusive. Defaults to the first of the "
        "month eleven months before `to`.",
    ),
    OpenApiParameter(
        "to",
        OpenApiTypes.DATE,
        description="Last day counted, inclusive. Defaults to today at the lab.",
    ),
]


class StatisticsView(APIView):
    """One section of the statistics over a period: validate, aggregate, return.

    Subclasses name their selector; the permission, the period parsing and the
    response are shared, so the five endpoints cannot drift apart on any of them.
    """

    permission_classes = [CanViewStatistics]
    selector = None

    @extend_schema(parameters=PERIOD_PARAMETERS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        """Return this section's statistics for the requested period."""
        query = PeriodQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(self.selector(query.validated_data))


class SummaryView(StatisticsView):
    """KPIs for the period against the one before it, and what is owed now."""

    selector = staticmethod(selectors.summary)


class VolumeView(StatisticsView):
    """Orders, stones, certificates and customers per bucket."""

    selector = staticmethod(selectors.volume)


class RevenueView(StatisticsView):
    """Billed, collected and outstanding money, per currency."""

    selector = staticmethod(selectors.revenue)


class TurnaroundView(StatisticsView):
    """Turnaround, stage bottlenecks, work-in-progress aging and workload."""

    selector = staticmethod(selectors.turnaround)


class MarketView(StatisticsView):
    """Species, origins, treatments, stone types and customer regions."""

    selector = staticmethod(selectors.market)
