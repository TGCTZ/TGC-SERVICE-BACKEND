from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_customer_region_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stone",
            name="weight_unit",
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
