# Implemented business rules

These are current code contracts, not a record of business approval. Update this
page when those contracts change. The sequence of work is described in
[Business workflow](business-workflow.md).

| Rule | Implementation |
| --- | --- |
| An order groups one customer's visit and submitted stone count | `Order`, `create_order()` |
| Stone registration requires a pricing category and is capped by the submitted count | `add_stone()` |
| A type, when supplied, must belong to the selected category | Stone serializers and `update_stone()` |
| Billing uses a flat fee per category, independent of weight | `preview_bill_for_order()`, `_create_local_bill()` |
| There is one bill per order, with copied line amounts | `Bill.order`, `BillItem` |
| Recorded payments may partially or fully settle a bill | `process_payment_notification()` |
| Findings require a fully paid bill | `_assert_payment_settled()` |
| Only one non-deleted identification report may exist per stone | `IdentificationReport` conditional constraint |
| Finalization through the API also issues the certificate | `IdentificationReportViewSet.finalize()` |
| Finalized findings can be corrected with a dedicated permission | `identification.edit_finalized_report`, `update_report()` |
| Corrections refresh certificate findings without replacing issuance metadata | `refresh_certificate_snapshot()` |
| No revoke action is exposed; historical revoked certificates still render | Certificate views, PDF renderer, public verification |
| A status transition records the previous and new status and actor | `transition_stone()`, `StatusHistory` |
| Account and role management follows role rank | `ROLE_RANKS`, user and role services |
| Staff create accounts; first login requires password and profile completion | Account services and `OnboardingJWTAuthentication` |

## References

`generate_reference_number()` allocates the order sequence for a July–June
financial year. Related documents derive that sequence with
`reference_number_for_order()`; they do not allocate separate counters.

| Document | Stored example | Display example |
| --- | --- | --- |
| Order | `ORD-2627-00042` | `ORD-26/27-00042` |
| Bill | `BILL-2627-00042` | `BILL-26/27-00042` |
| Findings for stone A | `TGC-2627-00042-A` | `TGC-26/27-00042-A` |
| Certificate for stone A | `CERT-2627-00042-A` | `CERT-26/27-00042-A` |

Stored values remain slash-free for gateway identifiers, filenames, and URLs.
`format_reference_number()` adds the slash for display. The allocator scans
deleted orders too and relies on the database constraint to reject concurrent
duplicates; it does not reserve a sequence under a database lock.

## Record relationships

```text
Customer -> Orders -> Stones -> Identification reports
               |         |                |
               Bill -> BillItems          Certificate
                |                     (findings snapshot)
             Payments
```

Reports are a foreign-key collection with at most one live report per stone.
Certificates retain a link to both their stone and source report. Reference
tables and enums are documented in [Reference data](reference-data.md).
