from django.db import migrations, models
import django.db.models.deletion


def backfill_stone_categories(apps, schema_editor):
    """Copy each existing type's pricing category onto its stones."""
    Stone = apps.get_model("orders", "Stone")
    database = schema_editor.connection.alias
    stones = (
        Stone._base_manager.using(database)
        .filter(stone_category__isnull=True)
        .select_related("stone_type")
    )
    for stone in stones.iterator(chunk_size=500):
        if stone.stone_type_id is None:
            raise RuntimeError(f"Stone {stone.pk} has no type to derive a category from")
        Stone._base_manager.using(database).filter(pk=stone.pk).update(
            stone_category_id=stone.stone_type.category_id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("gems", "0003_treatment"),
        ("orders", "0005_alter_stone_weight_unit"),
    ]

    operations = [
        migrations.AddField(
            model_name="stone",
            name="stone_category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stones",
                to="gems.stonecategory",
            ),
        ),
        migrations.RunPython(
            backfill_stone_categories,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="stone",
            name="stone_category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stones",
                to="gems.stonecategory",
            ),
        ),
        migrations.AlterField(
            model_name="stone",
            name="stone_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stones",
                to="gems.stonetype",
            ),
        ),
    ]
