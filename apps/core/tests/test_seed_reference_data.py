"""Shared setup seeds operational references and leaves finding lookups empty."""

import pytest

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from apps.gems.color_palette import COLORS
from apps.gems.enums import ColorGroup
from apps.gems.models import (
    Color,
    Instrument,
    Origin,
    ShapeCut,
    Species,
    StoneCategory,
    StoneType,
    Treatment,
    Variety,
)
from apps.users.models import Gender, UserStatus

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("history_months", [0, 1])
def test_demo_seed_runs_without_finding_lookups(history_months):
    """The development seeder does not depend on finding lookup rows."""
    call_command("seed", users=0, orders=0, history_months=history_months, verbosity=0)

    assert Species.objects.count() == 0
    assert Variety.objects.count() == 0
    assert Origin.objects.count() == 0
    assert ShapeCut.objects.count() == 0
    assert Treatment.objects.count() == 0


def test_shared_setup_creates_the_reference_baseline_and_roles():
    """The command seeds its baseline without pre-populating finding lookups."""
    call_command("seed_reference_data", verbosity=0)

    assert StoneCategory.objects.count() == 3
    assert StoneType.objects.count() == 8
    assert Color.objects.count() == 36
    assert Species.objects.count() == 0
    assert Variety.objects.count() == 0
    assert Origin.objects.count() == 0
    assert ShapeCut.objects.count() == 0
    assert Treatment.objects.count() == 0
    assert Instrument.objects.count() == 5
    assert UserStatus.objects.count() == 4
    assert Gender.objects.count() == 4
    assert Group.objects.filter(name="superadmin").exists()
    assert Group.objects.filter(name="accountant").exists()

    assert StoneCategory.objects.get(name="Precious").price == 30_000
    assert StoneType.objects.get(name="Ruby").category.name == "Precious"
    assert Color.objects.get(name="Red").group == ColorGroup.RED_PINK


def test_rerunning_shared_setup_preserves_other_edits_and_syncs_colors():
    """Other lookups retain edits while colors return to their canonical state."""
    call_command("seed_reference_data", verbosity=0)
    categories = {row.name: row for row in StoneCategory.objects.all()}

    # These fields are editable in an environment, so setup only supplies them
    # when first creating a row.
    categories["Precious"].price = 12_345
    categories["Precious"].save(update_fields=["price"])
    ruby = StoneType.objects.get(name="Ruby")
    ruby.category = categories["Diamond"]
    ruby.save(update_fields=["category"])
    red = Color.objects.get(name="Red")
    red.group = ColorGroup.BLUE
    red.save(update_fields=["group"])
    Group.objects.create(name="custom-role")
    custom_species = Species.objects.create(name="User entered species")
    custom_variety = Variety.objects.create(
        name="User entered variety", species=custom_species
    )
    custom_origin = Origin.objects.create(name="User entered origin")
    custom_shape = ShapeCut.objects.create(name="User entered shape")
    custom_treatment = Treatment.objects.create(name="User entered treatment")

    call_command("seed_reference_data", verbosity=0)

    assert StoneCategory.objects.count() == 3
    assert StoneType.objects.count() == 8
    assert StoneCategory.objects.get(name="Precious").price == 12_345
    assert StoneType.objects.get(name="Ruby").category.name == "Diamond"
    assert Color.objects.get(name="Red").group == ColorGroup.RED_PINK
    assert Color.objects.count() == 36
    assert Group.objects.filter(name="custom-role").exists()
    assert Species.objects.get(pk=custom_species.pk)
    assert Variety.objects.get(pk=custom_variety.pk)
    assert Origin.objects.get(pk=custom_origin.pk)
    assert ShapeCut.objects.get(pk=custom_shape.pk)
    assert Treatment.objects.get(pk=custom_treatment.pk)


def test_color_sync_makes_the_active_palette_exact_and_is_idempotent():
    """The dedicated command restores canonical rows and retires stale colors."""
    from apps.gems.models import Color

    retired = Color.objects.create(name="Legacy color", group=ColorGroup.BLUE)
    violet = Color.objects.create(name="Violet", group=ColorGroup.BLUE)
    violet.delete()

    call_command("sync_colors", verbosity=0)

    expected_groups = dict(COLORS)
    actual_groups = dict(Color.objects.values_list("name", "group"))
    assert actual_groups == expected_groups
    names = set(actual_groups)
    assert "Legacy color" not in names
    assert Color.all_objects.get(pk=retired.pk).is_deleted
    restored_violet = Color.objects.get(name="Violet")
    assert restored_violet.pk == violet.pk
    assert restored_violet.group == ColorGroup.PURPLE_VIOLET
    assert Color.objects.get(name="Brown").group == ColorGroup.BROWN

    call_command("sync_colors", verbosity=0)
    assert set(Color.objects.values_list("name", flat=True)) == names


def test_shared_setup_resynchronizes_declared_role_permissions():
    """Declared role permissions are refreshed from the code matrix."""
    call_command("seed_reference_data", verbosity=0)
    receptionist = Group.objects.get(name="receptionist")
    reports_permission = Permission.objects.get(
        content_type__app_label="core", codename="module_reports"
    )
    receptionist.permissions.add(reports_permission)

    call_command("seed_reference_data", verbosity=0)

    assert not receptionist.permissions.filter(pk=reports_permission.pk).exists()
