# Bill submission

## Local bill and submission

`generate_bill_for_order()` creates a bill and its lines in `_create_local_bill()`
before submitting it. It rejects an existing live bill, an order with no stones,
or any unpriced category. Stones move to `billed`; line prices come from each
stone's category. Bill references share the order's year and sequence.

The local operation has an atomic block. Under the API, `ATOMIC_REQUESTS` also
wraps the view: leaving that inner block is not a separate database commit.
Handled gateway failures return an outcome rather than raising, allowing the
local bill to persist when the request commits.

`build_bill_xml()` is the source for exact wire fields. It emits `BillHdr`,
`BillDtls/BillDtl`, and `BillItems/BillItem` inside `billSubReq`. Amounts are
two-decimal strings; bill identifiers remain slash-free. Customer text is
escaped, phone numbers are normalized, and the customer ID is zero-padded.
`BillPayOpt` is `3`; `MinPayAmt` is the full bill amount.

`submit_bill()` signs and persists this exact XML before POSTing it with
`Content-Type: application/xml`, configured `Gepg-Com` and `Gepg-Alg`, and
`Gepg-Code` from settings. Transport failures retry the stored payload with
bounded exponential backoff for up to 24 hours. Business rejections are not
retried.

## Control numbers

| Response | Stored behavior |
| --- | --- |
| `billSubRes` with `BillStsCode=7101` and a nonzero control number | Save the number and status fields |
| Accepted `billSubReqAck` (`7101`) | Keep control number empty pending callback |
| `billSubReqAck` with `7241` | Treat as invalid session; do not mark accepted |
| Rejection or handled connection/parsing error | Keep the local bill and failure details |

`PENDING` is an internal result marker and is not stored as a control number
by the submission service. `is_gepg_submitted` records an attempted submission,
including a failed one; it does not prove acceptance.

`POST /gepg/bill/response/` extracts `ResId`, `BillId`, `BillCntrNum`, and status
fields. Inbound signature verification is controlled by
`GEPG_VERIFY_CALLBACK_SIGNATURE` and defaults to `False` for legacy
compatibility. The callback is stored before it is acknowledged. A matching bill
receives a control number only when its bill-level status is `7101` and the
number is neither empty nor `0`. Unknown bills are recorded as failures for
staff review.

## Automatic billing and retries

Automatic registration uses `identify_stone()` after saving the stone. It bills
only when the registered count equals the submitted count and the order is not
held. Handled pricing failures leave the stone registered with an attention message.

In automatic mode, `GET /api/v1/bills/attention/` lists affected orders and
`POST /api/v1/bills/retry/` accepts `{"order": 123}`. Both require
`billing.generate_bill`; both return 404 in manual mode. A retry creates a
missing bill for a fully registered order or resubmits its existing failed bill
without replacing lines, number, or stone statuses. Held orders are refused.

An existing bill needs attention only when it is `pending`, has no control
number, and has no accepted acknowledgement code. Accepted asynchronous bills
wait for their callback. The PostgreSQL timer retries persisted transport failures;
exhausted requests remain visible to staff in the GePG outbound-request admin.
