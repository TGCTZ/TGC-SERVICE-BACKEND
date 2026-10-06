"""Add Brown as a color family."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gems", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="color",
            name="group",
            field=models.CharField(
                choices=[
                    ("white_grey_black", "White/Grey/Black"),
                    ("purple_violet", "Purple/Violet"),
                    ("red_pink", "Red/Pink"),
                    ("orange_yellow", "Orange/Yellow"),
                    ("green", "Green"),
                    ("blue", "Blue"),
                    ("brown", "Brown"),
                ],
                max_length=20,
            ),
        ),
    ]
