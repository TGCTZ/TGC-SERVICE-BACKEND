"""Health-check endpoints for load balancers and orchestrators."""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import connections
from django.db.migrations.executor import MigrationExecutor


class LivenessView(APIView):
    """Report that the process is running.

    Touches nothing external, so it stays true while a dependency is down. A
    liveness probe that queried the database would have the orchestrator restart
    a perfectly healthy container every time the database blinked.
    """

    permission_classes = [AllowAny]
    authentication_classes = ()
    throttle_classes = ()

    @extend_schema(
        summary="Liveness probe",
        responses=inline_serializer(
            name="Liveness", fields={"status": serializers.CharField()}
        ),
        auth=[],
    )
    def get(self, request):
        """Return 200 for as long as the process can serve requests."""
        return Response({"status": "ok"})


class ReadinessView(APIView):
    """Report whether the service can actually handle traffic.

    Checks the things a request would need: a usable database connection and a
    fully migrated schema. Returns 503 when either fails, so a rolling deploy
    holds back traffic instead of routing it into errors.
    """

    permission_classes = [AllowAny]
    authentication_classes = ()
    throttle_classes = ()

    @extend_schema(
        summary="Readiness probe",
        responses=inline_serializer(
            name="Readiness",
            fields={
                "status": serializers.CharField(),
                "checks": serializers.DictField(child=serializers.CharField()),
            },
        ),
        auth=[],
    )
    def get(self, request):
        """Return 200 when every dependency check passes, 503 otherwise."""
        checks = {
            "database": self._check_database(),
            "migrations": self._check_migrations(),
        }
        healthy = all(result == "ok" for result in checks.values())
        return Response(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def _check_database(self) -> str:
        """Confirm the default connection can execute a trivial query."""
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as exc:  # any failure at all means "not ready"
            return f"error: {exc.__class__.__name__}"
        return "ok"

    def _check_migrations(self) -> str:
        """Confirm no migration is left unapplied.

        A container serving traffic against a half-migrated schema fails in ways
        that are far harder to diagnose than a failed readiness probe.
        """
        try:
            executor = MigrationExecutor(connections["default"])
            targets = executor.loader.graph.leaf_nodes()
            pending = executor.migration_plan(targets)
        except Exception as exc:  # any failure at all means "not ready"
            return f"error: {exc.__class__.__name__}"
        return "ok" if not pending else f"{len(pending)} unapplied"
