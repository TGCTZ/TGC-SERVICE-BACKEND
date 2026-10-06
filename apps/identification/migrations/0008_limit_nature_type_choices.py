"""Limit report nature values to the classifications used by the lab."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Update Django's field choices without rewriting historical values."""

    dependencies = [
        ('identification', '0007_empty_finding_lookups'),
    ]

    operations = [
        migrations.AlterField(
            model_name='identificationreport',
            name='nature_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ("natural", "Natural"),
                    ("artificial", "Artificial"),
                    ("synthetic", "Synthetic"),
                ],
                default="",
                max_length=20,
            ),
        ),
    ]
