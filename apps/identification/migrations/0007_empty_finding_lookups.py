"""Remove the initial finding lookup data and clear report references."""

from django.db import migrations


def empty_finding_lookups(apps, schema_editor):
    """Permanently empty the five finding lookups, including deleted rows."""
    db = schema_editor.connection.alias
    report_model = apps.get_model("identification", "IdentificationReport")
    report_model._base_manager.using(db).all().update(
        species=None,
        variety=None,
        origin=None,
        shape_cut=None,
        treatment=None,
    )

    # Delete children before parents because Variety protects its Species.
    for model_name in ("Variety", "Species", "Origin", "ShapeCut", "Treatment"):
        model = apps.get_model("gems", model_name)
        model._base_manager.using(db).all().delete()


class Migration(migrations.Migration):
    """Clear finding references and permanently delete their lookup rows."""

    dependencies = [
        ("gems", "0003_treatment"),
        ("identification", "0006_alter_identificationreport_treatment"),
    ]

    operations = [
        migrations.RunPython(
            empty_finding_lookups,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
