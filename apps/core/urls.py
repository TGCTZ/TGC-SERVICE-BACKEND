"""Health-check routes.

Mounted outside the ``/api/v1/`` prefix: probes are infrastructure, not part of
the versioned API contract, and must keep working across a version bump.
"""

from django.urls import path

from .views import LivenessView, ReadinessView

urlpatterns = [
    path("health/", LivenessView.as_view(), name="health-live"),
    path("health/ready/", ReadinessView.as_view(), name="health-ready"),
]
