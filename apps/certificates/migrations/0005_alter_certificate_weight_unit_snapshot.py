from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("certificates", "0004_alter_certificate_treatment_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="certificate",
            name="weight_unit_snapshot",
            field=models.CharField(
                choices=[
                    ("carat", "Carat"),
                    ("gram", "Gram"),
                    ("kilogram", "Kilogram"),
                ],
                default="carat",
                max_length=10,
            ),
        ),
    ]
