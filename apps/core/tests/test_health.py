"""Health-check endpoints."""

import pytest

pytestmark = pytest.mark.django_db


def test_liveness_needs_no_authentication(api_client):
    """Probes cannot log in, so this must answer without a token."""
    response = api_client.get("/api/health/")

    assert response.status_code == 200
    assert response.data == {"status": "ok"}


def test_readiness_needs_no_authentication(api_client):
    """Readiness is infrastructure, not part of the authenticated API."""
    response = api_client.get("/api/health/ready/")

    assert response.status_code == 200


def test_readiness_reports_each_dependency(api_client):
    """The payload names what was checked, so a failure is diagnosable."""
    response = api_client.get("/api/health/ready/")

    assert response.data["status"] == "ok"
    assert response.data["checks"] == {"database": "ok", "migrations": "ok"}


def test_readiness_returns_503_when_the_database_is_unreachable(api_client, monkeypatch):
    """A dependency failure must fail the probe, not raise a 500.

    503 tells an orchestrator to hold traffic back; a 500 looks like an
    application bug and gets routed to anyway.
    """
    from apps.core import views

    monkeypatch.setattr(
        views.ReadinessView, "_check_database", lambda self: "error: OperationalError"
    )
    response = api_client.get("/api/health/ready/")

    assert response.status_code == 503
    assert response.data["status"] == "degraded"


def test_health_is_excluded_from_the_versioned_api(api_client):
    """Probes live outside /api/v1/ so a version bump cannot break them."""
    assert api_client.get("/api/v1/health/").status_code == 404
