"""Persist GePG callbacks and exact outbound requests for recovery."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_reconciliationtransaction_bill_pay_opt_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GePGCallback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("kind", models.CharField(choices=[("payment", "Payment notification"), ("bill", "Bill response"), ("cancellation", "Cancellation response"), ("reconciliation", "Reconciliation response")], max_length=20)),
                ("event_id", models.CharField(max_length=100)),
                ("payload", models.TextField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("processed", "Processed"), ("failed", "Failed")], db_index=True, default="pending", max_length=20)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["status", "created_at"], name="bill_gepgcb_status_created_idx")],
            },
        ),
        migrations.CreateModel(
            name="GePGRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("operation", models.CharField(choices=[("bill", "Bill submission"), ("cancellation", "Bill cancellation"), ("reconciliation", "Reconciliation request")], max_length=20)),
                ("req_id", models.CharField(max_length=100, unique=True)),
                ("endpoint", models.URLField(max_length=500)),
                ("gepg_com", models.CharField(max_length=100)),
                ("gepg_code", models.CharField(max_length=100)),
                ("gepg_alg", models.CharField(max_length=100)),
                ("payload", models.TextField()),
                ("status", models.CharField(choices=[("sending", "Sending"), ("retry", "Waiting to retry"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("exhausted", "Retries exhausted")], db_index=True, default="sending", max_length=20)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("first_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("next_attempt_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("response_xml", models.TextField(blank=True, default="")),
                ("last_error", models.TextField(blank=True, default="")),
                ("status_code", models.CharField(blank=True, default="", max_length=30)),
                ("status_desc", models.CharField(blank=True, default="", max_length=255)),
                ("bill", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="gepg_requests", to="billing.bill")),
                ("cancellation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="gepg_requests", to="billing.billcancellation")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("reconciliation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="gepg_requests", to="billing.reconciliation")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["status", "next_attempt_at"], name="bill_gepgreq_status_next_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="gepgcallback",
            constraint=models.UniqueConstraint(condition=models.Q(("deleted_at__isnull", True)), fields=("kind", "event_id"), name="billing_gepgcallback_unique_event"),
        ),
    ]
