# GePG integration

The gateway submits bills, returns control numbers, and exchanges payment,
cancellation, and reconciliation messages. These pages describe this adapter,
not the full GePG protocol.

| Guide | Purpose |
| --- | --- |
| [Overview](00_GEPG_INTEGRATION_OVERVIEW.md) | Modules, configuration, and current limitations |
| [Flow diagrams](03_GEPG_FLOW_DIAGRAMS.md) | End-to-end visual guide to billing, callbacks, settlement, retries, and simulation |
| [Bill submission](01_BILL_SUBMISSION.md) | Local billing, submission, retries, and control-number callbacks |
| [Payment notifications](02_PAYMENT_NOTIFICATION.md) | Parsing, settlement, acknowledgements, and duplicate handling |
| [Production setup](04_GEPG_PRODUCTION_SETUP.md) | VPS secrets, PFX provisioning, callback routing, and pre-cutover checks |

## Working offline

`GEPG_SIMULATE=True` makes outbound submission return a generated control number
without calling GePG. This gateway switch itself does not check `DEBUG`.
The API's `POST /api/v1/bills/{id}/simulate-payment/` action requires **both**
`DEBUG` and `GEPG_SIMULATE`, plus `billing.generate_bill`.

Simulation feeds generated XML through the payment handler. An omitted amount
pays the outstanding balance; a smaller amount exercises partial settlement.
See [`apps/billing/dev.py`](../../apps/billing/dev.py).

## Current limitations

- Inbound callbacks do not verify signatures. `GEPG_PUBLIC_CERT_PATH` is read
  into settings but not used for verification. A forged matching notification
  can affect payment state.
- When signing is enabled, a missing or invalid PFX fails the outbound operation;
  the adapter does not send placeholder signatures after signing errors.
- Retries are explicit API actions, not a scheduled queue. Accepted submissions
  without a control number wait for the callback and are not retry candidates.
- Cancellation and reconciliation API actions are implemented, but the old
  cancellation endpoint was described as a mock and neither flow is live-verified.
- Beem SMS is sent when a control number is available; delivery depends on
  provider availability and configured credentials.

These limitations describe running code; they are not guarantees of gateway
compatibility or authentication.
