# Payment notifications

`POST /gepg/payments/notification/` passes its decoded request body to
`process_payment_notification()`. The response is acknowledgement XML, with
optional signing controlled by `GEPG_USE_DIGITAL_SIGNATURE`.

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

Successful handling returns `pmtSpNtfReqAck` with code `7101`. Caught XML/value
parsing errors and caught application errors return `7102`. The parser can also
raise errors outside its caught exception set, so callers must not assume that
every malformed payload receives XML.

Each `_apply_payment()` call is atomic. The notification loop can return a
failure acknowledgement after an earlier transaction has succeeded; it does not
guarantee all-or-nothing processing of a multi-transaction notification.

Request examples are in [`api.http`](../../api.http). Use the same transaction ID
to exercise redelivery, a new ID for another payment, and a smaller amount to
exercise partial settlement. Use the [simulation helper](README.md#working-offline)
when the real gateway is unavailable.

Inbound signatures are not verified; see the [integration limitations](README.md#current-limitations).
