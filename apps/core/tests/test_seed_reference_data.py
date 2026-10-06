"""The shared setup creates canonical rows and synchronizes the color palette."""

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
    Variety,
)
from apps.users.models import Gender, UserStatus

pytestmark = pytest.mark.django_db


def test_shared_setup_creates_the_reference_baseline_and_roles():
    """The command materializes all agreed reference rows and roles."""
    call_command("seed_reference_data", verbosity=0)

    assert StoneCategory.objects.count() == 3
    assert StoneType.objects.count() == 8
    assert Species.objects.count() == 4
    assert Variety.objects.count() == 9
    assert Color.objects.count() == 36
    assert Origin.objects.count() == 5
    assert ShapeCut.objects.count() == 5
    assert Instrument.objects.count() == 5
    assert UserStatus.objects.count() == 4
    assert Gender.objects.count() == 4
    assert Group.objects.filter(name="superadmin").exists()
    assert Group.objects.filter(name="accountant").exists()

    assert StoneCategory.objects.get(name="Precious").price == 30_000
    assert StoneType.objects.get(name="Ruby").category.name == "Precious"
    assert Color.objects.get(name="Red").group == ColorGroup.RED_PINK
    assert Variety.objects.filter(name="Ruby", species__name="Corundum").exists()


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

    call_command("seed_reference_data", verbosity=0)

    assert StoneCategory.objects.count() == 3
    assert StoneType.objects.count() == 8
    assert StoneCategory.objects.get(name="Precious").price == 12_345
    assert StoneType.objects.get(name="Ruby").category.name == "Diamond"
    assert Color.objects.get(name="Red").group == ColorGroup.RED_PINK
    assert Color.objects.count() == 36
    assert Group.objects.filter(name="custom-role").exists()


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
