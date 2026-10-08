from django.db import migrations


def remove_revoke_permission(apps, schema_editor):
    """Remove the obsolete action permission and its group/user grants."""
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="certificates",
        codename="revoke_certificate",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("certificates", "0005_alter_certificate_weight_unit_snapshot"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="certificate",
            options={
                "ordering": ["-issued_at"],
                "permissions": [("issue_certificate", "Can issue a certificate")],
            },
        ),
        migrations.RunPython(remove_revoke_permission, migrations.RunPython.noop),
    ]
