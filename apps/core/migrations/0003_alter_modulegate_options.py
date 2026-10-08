"""Create report permissions and retain access granted by source permissions."""

from django.conf import settings
from django.db import migrations

FINANCIAL_SOURCES = {("billing", "view_bill"), ("billing", "view_payment")}
OPERATIONAL_SOURCES = {
    ("orders", "view_order"),
    ("orders", "view_stone"),
    ("identification", "view_identificationreport"),
    ("certificates", "view_certificate"),
}


def preserve_report_access(apps, schema_editor):
    """Give current report readers the new gates without resetting edited roles."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    user_app, user_model = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app, user_model)
    content_type, _ = ContentType.objects.using(
        schema_editor.connection.alias
    ).get_or_create(app_label="core", model="modulegate")
    gates = {}
    for codename, name in (
        ("module_reports", "Can access the reports module"),
        ("report_financial", "Can access financial reports"),
        ("report_operational", "Can access operational reports"),
    ):
        gates[codename], _ = Permission.objects.using(
            schema_editor.connection.alias
        ).get_or_create(
            content_type=content_type, codename=codename, defaults={"name": name}
        )

    for holders, relation in (
        (Group.objects, "permissions"),
        (User.objects, "user_permissions"),
    ):
        for holder in holders.using(schema_editor.connection.alias).all().iterator():
            source_permissions = set(
                getattr(holder, relation).values_list(
                    "content_type__app_label", "codename"
                )
            )
            page_gates = []
            if source_permissions & FINANCIAL_SOURCES:
                page_gates.append(gates["report_financial"])
            if source_permissions & OPERATIONAL_SOURCES:
                page_gates.append(gates["report_operational"])
            if page_gates:
                getattr(holder, relation).add(gates["module_reports"], *page_gates)


class Migration(migrations.Migration):
    """Declare the report gates and grant them to existing readers."""

    dependencies = [
        ("core", "0002_alter_modulegate_options"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="modulegate",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": [
                    ("module_orders", "Can access the orders module"),
                    ("module_identification", "Can access the identification module"),
                    ("module_billing", "Can access the billing module"),
                    ("module_reports", "Can access the reports module"),
                    ("report_financial", "Can access financial reports"),
                    ("report_operational", "Can access operational reports"),
                    ("module_certificates", "Can access the certificates module"),
                    ("module_reference", "Can access the reference-data module"),
                    ("module_user", "Can access the user module"),
                    ("module_settings", "Can access the settings module"),
                    ("module_audit", "Can access the audit module"),
                ],
            },
        ),
        migrations.RunPython(preserve_report_access, migrations.RunPython.noop),
    ]
