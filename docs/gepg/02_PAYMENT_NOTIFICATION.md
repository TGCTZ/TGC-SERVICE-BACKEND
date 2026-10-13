# Payment notifications

`POST /gepg/payments/notification/` verifies the request signature, stores the
callback in the PostgreSQL inbox, and queues `process_payment_notification()`.
The endpoint acknowledges only after persistence and queue submission succeed.

## Parsing and settlement

`parse_payment_notification()` uses `defusedxml` and requires a `PmtHdr` and at
least one `PmtTrxDtl`. It returns the header plus transaction dictionaries,
including bill identifiers, transaction ID, amounts, currency, payment provider,
transaction timestamp, and payer fields. Exact tag mappings are in
[`gateways/gepg.py`](../../apps/billing/gateways/gepg.py).

For each transaction, `_apply_payment()`:

1. Finds the bill by `BillId`, falling back to `BillCtrNum`.
2. Creates a `Payment` keyed by `trx_id`, storing parsed fields and raw XML.
3. For a new payment, sums the bill's live payment amounts. A total covering
   the bill sets `paid`, moves its stones to `paid`, and notifies bill-paid
   subscribers. A lower total sets `partially_paid`.
4. For an existing transaction ID, updates the stored payment and returns
   without recomputing settlement or repeating the transitions.

Identical redelivery avoids a second payment row. A changed amount under an
existing transaction ID is **not** reconciled into bill status by this handler.
Settlement sums payment amounts without currency conversion or an
`is_processed` filter; this differs from the reporting balance calculation.

## Acknowledgements and transactions

Successful processing returns `pmtSpNtfReqAck` with code `7101`. Invalid
request data uses `7242`, an unknown bill uses `7204`, and an internal processing
failure uses `7321`. The callback endpoint rejects invalid signatures with
`7303`; broker/database outages return HTTP 503 for redelivery.

Each `_apply_payment()` call is atomic and idempotent on GePG transaction ID.
Reconciliation responses use the same path, so a transaction missed by a
notification can still settle its bill without creating a duplicate payment.

Request examples are in [`api.http`](../../api.http). Use the same transaction ID
to exercise redelivery, a new ID for another payment, and a smaller amount to
exercise partial settlement. Use the [simulation helper](README.md#working-offline)
when the real gateway is unavailable.

See the [production setup](04_GEPG_PRODUCTION_SETUP.md) for callback signing
certificates, Redis workers, and retry monitoring.
