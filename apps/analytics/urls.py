"""URL routes for the management statistics."""

from django.urls import path

from .views import MarketView, RevenueView, SummaryView, TurnaroundView, VolumeView

urlpatterns = [
    path("analytics/summary/", SummaryView.as_view(), name="analytics-summary"),
    path("analytics/volume/", VolumeView.as_view(), name="analytics-volume"),
    path("analytics/revenue/", RevenueView.as_view(), name="analytics-revenue"),
    path("analytics/turnaround/", TurnaroundView.as_view(), name="analytics-turnaround"),
    path("analytics/market/", MarketView.as_view(), name="analytics-market"),
]
