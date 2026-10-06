"""The one-time migration clears finding lookups without rewriting certificates."""

import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest

from django.apps import apps
from django.db import connection
from django.utils import timezone

from apps.certificates.models import Certificate
from apps.gems.models import Color, Origin, ShapeCut, Species, Treatment, Variety
from apps.gems.tests.factories import (
    ColorFactory,
    OriginFactory,
    ShapeCutFactory,
    SpeciesFactory,
    TreatmentFactory,
    VarietyFactory,
)
from apps.identification.models import IdentificationReport
from apps.orders.tests.factories import StoneFactory

pytestmark = pytest.mark.django_db


def test_cleanup_clears_report_references_and_preserves_certificate_snapshots():
    """Every finding lookup is deleted, while the issued document stays frozen."""
    species = SpeciesFactory(name="Corundum")
    variety = VarietyFactory(name="Ruby", species=species)
    origin = OriginFactory(name="Mogok")
    deleted_origin = OriginFactory(name="Retired origin")
    deleted_origin.delete()
    shape_cut = ShapeCutFactory(name="Oval")
    treatment = TreatmentFactory(name="Heated")
    color = ColorFactory(name="Red")
    stone = StoneFactory()
    report = IdentificationReport.objects.create(
        stone=stone,
        report_number="RPT-CLEANUP-1",
        species=species,
        variety=variety,
        origin=origin,
        shape_cut=shape_cut,
        treatment=treatment,
        color=color,
    )
    certificate = Certificate.objects.create(
        stone=stone,
        report=report,
        certificate_number="CERT-CLEANUP-1",
        stone_type_snapshot=stone.stone_type.name,
        weight_snapshot=Decimal("1.250"),
        species_snapshot=species.name,
        variety_snapshot=variety.name,
        origin_snapshot=origin.name,
        shape_cut_snapshot=shape_cut.name,
        treatment_snapshot=treatment.name,
        issued_at=timezone.now(),
    )

    migration = importlib.import_module(
        "apps.identification.migrations.0007_empty_finding_lookups"
    )
    migration.empty_finding_lookups(apps, SimpleNamespace(connection=connection))

    report.refresh_from_db()
    certificate.refresh_from_db()
    assert report.species_id is None
    assert report.variety_id is None
    assert report.origin_id is None
    assert report.shape_cut_id is None
    assert report.treatment_id is None
    assert report.color_id == color.pk
    assert certificate.species_snapshot == "Corundum"
    assert certificate.variety_snapshot == "Ruby"
    assert certificate.origin_snapshot == "Mogok"
    assert certificate.shape_cut_snapshot == "Oval"
    assert certificate.treatment_snapshot == "Heated"
    assert Species.all_objects.count() == 0
    assert Variety.all_objects.count() == 0
    assert Origin.all_objects.count() == 0
    assert ShapeCut.all_objects.count() == 0
    assert Treatment.all_objects.count() == 0
    assert Color.objects.filter(pk=color.pk).exists()
