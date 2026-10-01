"""Shared report querysets, projections and totals for screen and exports.

Amounts are aggregated before pagination. Payment sums use a correlated subquery
so joining an order's stones cannot multiply the money attributed to its bill.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest, NullIf
from django.utils import timezone

from apps.billing.models import Bill, Payment
from apps.certificates.models import Certificate
from apps.gems.enums import BillStatus
from apps.identification.models import IdentificationReport
from apps.orders.models import Order, Stone

from .definitions import REPORT_TIMEZONE, section_info

MONEY_FIELD = DecimalField(max_digits=18, decimal_places=2)


def _bill_source():
    return Bill.objects.select_related("order__customer").filter(
        order__deleted_at__isnull=True, order__customer__deleted_at__isnull=True
    )


def _outstanding_source():
    payments = (
        Payment.objects.filter(bill_id=OuterRef("pk"), is_processed=True)
        .filter(Q(currency="") | Q(currency=OuterRef("currency")))
        .order_by()
        .values("bill_id")
        .annotate(amount=Sum("paid_amount"))
        .values("amount")
    )
    return (
        _bill_source()
        .exclude(status=BillStatus.CANCELLED)
        .annotate(
            amount_paid=Coalesce(
                Subquery(payments, output_field=MONEY_FIELD), Decimal(0)
            ),
        )
        .annotate(
            balance=Greatest(
                F("total_amount") - F("amount_paid"), Decimal(0), output_field=MONEY_FIELD
            )
        )
        .filter(balance__gt=0)
    )


def _source(key):
    if key in ("billing", "outstanding"):
        source = _outstanding_source() if key == "outstanding" else _bill_source()
        return source, "issued_at", "order__customer"
    if key in ("collections", "exceptions"):
        source = (
            Payment.objects.select_related("bill__order__customer")
            .filter(is_processed=key == "collections")
            .filter(
                Q(bill__isnull=True)
                | Q(
                    bill__deleted_at__isnull=True,
                    bill__order__deleted_at__isnull=True,
                    bill__order__customer__deleted_at__isnull=True,
                )
            )
            .annotate(
                report_currency=Coalesce(
                    NullIf("currency", Value("")), "bill__currency", Value("Unknown")
                )
            )
        )
        return source, "trx_dt_tm", "bill__order__customer"
    if key == "orders":
        return (
            Order.objects.select_related("customer").filter(
                customer__deleted_at__isnull=True
            ),
            "received_date",
            "customer",
        )
    if key == "stones":
        source = Stone.objects.select_related("order__customer", "stone_type")
        date_field = "created_at"
        customer_path = "order__customer"
        parent_path = "order"
    else:
        model = IdentificationReport if key == "findings" else Certificate
        source = model.objects.select_related(
            "stone__order__customer", "stone__stone_type"
        )
        date_field = "identified_at" if key == "findings" else "issued_at"
        customer_path = "stone__order__customer"
        parent_path = "stone__order"
        source = source.filter(stone__deleted_at__isnull=True)
        if key == "findings":
            source = source.filter(is_finalized=True)
    return (
        source.filter(
            **{
                f"{parent_path}__deleted_at__isnull": True,
                f"{customer_path}__deleted_at__isnull": True,
            }
        ),
        date_field,
        customer_path,
    )


def section_queryset(key: str, filters: dict):
    """Return dated rows and an undated count after applying relevant filters."""
    queryset, date_field, customer_path = _source(key)
    if filters.get("customer"):
        queryset = queryset.filter(**{customer_path: filters["customer"]})
    if key in ("billing", "outstanding") and filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    if key in ("collections", "exceptions") and filters.get("provider"):
        queryset = queryset.filter(psp_code=filters["provider"])
    if key in ("orders", "stones", "findings", "certificates") and filters.get(
        "stone_type"
    ):
        path = {
            "orders": "stones",
            "stones": "",
            "findings": "stone",
            "certificates": "stone",
        }[key]
        prefix = f"{path}__" if path else ""
        stone_filters = {f"{prefix}stone_type": filters["stone_type"]}
        if key == "orders":
            # Both predicates must refer to the same stone in this to-many join.
            stone_filters["stones__deleted_at__isnull"] = True
        queryset = queryset.filter(**stone_filters)
        if key == "orders":
            queryset = queryset.distinct()
    missing_dates = queryset.filter(**{f"{date_field}__isnull": True}).count()
    if key == "orders":
        queryset = queryset.filter(
            received_date__range=(filters["from_date"], filters["to_date"])
        )
    else:
        start = datetime.combine(filters["from_date"], time.min, REPORT_TIMEZONE)
        end = datetime.combine(filters["to_date"], time.min, REPORT_TIMEZONE) + timedelta(
            days=1
        )
        queryset = queryset.filter(
            **{f"{date_field}__gte": start, f"{date_field}__lt": end}
        )
    return queryset.order_by(f"-{date_field}", "-pk"), missing_dates


def section_summary(key: str, queryset, missing_dates: int) -> dict:
    """Compute totals from the entire filtered queryset using decimal arithmetic."""
    amounts = []
    if key in ("billing", "outstanding", "collections", "exceptions"):
        currency_field = (
            "report_currency" if key in ("collections", "exceptions") else "currency"
        )
        amount_field = {
            "billing": "total_amount",
            "outstanding": "balance",
            "collections": "paid_amount",
            "exceptions": "paid_amount",
        }[key]
        amounts = [
            {
                "currency": row[currency_field],
                "amount": str(row["amount"] or Decimal("0.00")),
            }
            for row in queryset.order_by()
            .values(currency_field)
            .annotate(amount=Sum(amount_field))
            .order_by(currency_field)
        ]
    statuses = []
    if key in ("billing", "outstanding"):
        statuses = list(
            queryset.order_by()
            .values("status")
            .annotate(count=Count("pk"))
            .order_by("status")
        )
    return {
        **section_info(key),
        "count": queryset.count(),
        "missing_dates": missing_dates,
        "amounts": amounts,
        "statuses": statuses,
    }


def report_sections(keys: list[str], filters: dict) -> dict:
    """Keep querysets unevaluated so screen requests only fetch their selected page."""
    sections = {}
    for key in keys:
        queryset, missing_dates = section_queryset(key, filters)
        sections[key] = {
            "queryset": queryset,
            "summary": section_summary(key, queryset, missing_dates),
        }
    return sections


def report_filters(keys: list[str]) -> dict:
    """Derive filter choices from permitted sources, without broad customer access."""
    customers = {}
    stone_types = {}
    providers = {}
    for key in keys:
        queryset, _, customer_path = _source(key)
        fields = [
            f"{customer_path}__{field}"
            for field in ("id", "first_name", "middle_name", "last_name")
        ]
        for row in queryset.order_by().values_list(*fields).distinct():
            if row[0] is not None:
                customers[row[0]] = " ".join(part for part in row[1:] if part)
        if key in ("collections", "exceptions"):
            providers.update(
                queryset.order_by()
                .exclude(psp_code="")
                .values_list("psp_code", "psp_name")
                .distinct()
            )
        if key in ("orders", "stones", "findings", "certificates"):
            path = {
                "orders": "stones__stone_type",
                "stones": "stone_type",
                "findings": "stone__stone_type",
                "certificates": "stone__stone_type",
            }[key]
            choices = queryset
            if key == "orders":
                choices = choices.filter(stones__deleted_at__isnull=True)
            for pk, name in (
                choices.order_by().values_list(f"{path}__id", f"{path}__name").distinct()
            ):
                if pk is not None:
                    stone_types[pk] = name
    return {
        "customers": [
            {"id": pk, "label": name}
            for pk, name in sorted(customers.items(), key=lambda item: item[1])
        ],
        "stone_types": [
            {"id": pk, "label": name}
            for pk, name in sorted(stone_types.items(), key=lambda item: item[1])
        ],
        "providers": [
            {"id": code, "label": name or code}
            for code, name in sorted(providers.items())
        ],
    }


def report_columns(key: str) -> list[dict]:
    """Match the exact row projection; money and dates have explicit display types."""
    fields = [
        ("event_date", "Date", "date"),
        ("reference", "Reference", "text"),
        ("customer", "Customer", "text"),
    ]
    if key != "orders":
        fields.append(("order", "Order", "text"))
    if key in ("billing", "outstanding", "collections", "exceptions"):
        fields += [("currency", "Currency", "text"), ("amount", "Amount", "money")]
        if key == "outstanding":
            fields += [
                ("paid", "Paid so far", "money"),
                ("balance", "Owed today", "money"),
            ]
        if key in ("collections", "exceptions"):
            fields.append(("provider", "Payment provider", "text"))
    else:
        fields.append(
            ("stones", "Submitted stones", "text")
            if key == "orders"
            else ("stone_type", "Stone type", "text")
        )
    if key != "orders":
        fields.append(("status", "Current status", "text"))
    return [{"key": field, "label": label, "kind": kind} for field, label, kind in fields]


def report_rows(key: str, objects) -> list[dict]:
    """Project joined objects without exposing findings, gateway payloads or tokens."""
    rows = []
    for obj in objects:
        if key in ("collections", "exceptions"):
            order = obj.bill.order if obj.bill_id else None
            event_date = obj.trx_dt_tm
            row = {
                "reference": obj.trx_id or obj.pay_ref_id,
                "currency": obj.report_currency,
                "amount": str(obj.paid_amount or Decimal("0.00")),
                "provider": obj.psp_name or obj.psp_code,
                "status": "Processed" if obj.is_processed else "Unprocessed",
            }
        elif key in ("billing", "outstanding"):
            order, event_date = obj.order, obj.issued_at
            row = {
                "reference": obj.bill_number,
                "currency": obj.currency,
                "amount": str(obj.total_amount),
                "status": obj.get_status_display(),
            }
            if key == "outstanding":
                row.update(paid=str(obj.amount_paid), balance=str(obj.balance))
        elif key == "orders":
            order, event_date = obj, obj.received_date
            row = {"reference": obj.reference_number, "stones": obj.stone_count}
        else:
            stone = obj if key == "stones" else obj.stone
            order = stone.order
            event_date = (
                obj.created_at
                if key == "stones"
                else (obj.identified_at if key == "findings" else obj.issued_at)
            )
            reference = (
                stone.label
                if key == "stones"
                else (obj.report_number if key == "findings" else obj.certificate_number)
            )
            row = {
                "reference": reference,
                "stone_type": stone.stone_type.name,
                "status": "Finalized" if key == "findings" else obj.get_status_display(),
            }
        local_date = (
            timezone.localtime(event_date, REPORT_TIMEZONE).date()
            if isinstance(event_date, datetime)
            else event_date
        )
        rows.append(
            {
                "id": obj.pk,
                "event_date": local_date.isoformat(),
                "customer": order.customer.full_name if order else obj.pyr_name,
                "order": order.reference_number if order else "",
                **row,
            }
        )
    return rows
