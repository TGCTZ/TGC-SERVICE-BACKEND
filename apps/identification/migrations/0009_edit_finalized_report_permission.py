"""Add the dedicated finalized-report correction permission."""

from django.db import migrations


class Migration(migrations.Migration):
    """Register the correction permission with Django's permission system."""

    dependencies = [("identification", "0008_limit_nature_type_choices")]

    operations = [
        migrations.AlterModelOptions(
            name="identificationreport",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    ("finalize_report", "Can finalize an identification report"),
                    (
                        "edit_finalized_report",
                        "Can edit a finalized identification report",
                    ),
                ],
            },
        ),
    ]
