from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0006_stone_category_and_optional_type"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="customer",
            name="orders_customer_unique_phone",
        ),
    ]
