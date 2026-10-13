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

- Inbound callback signatures are verified against the configured GePG public
  certificate before callbacks enter the durable inbox. Production settings
  require signing and the registered `GEPG_COM` and `GEPG_ALG` values.
- Callback processing and outbound retries run through Celery and Redis. The
  PostgreSQL inbox/outbox records support recovery after worker or broker
  interruptions; application rejections are not automatically retried.
- Accepted asynchronous submissions without a control number wait for the
  callback and are not outbound retry candidates.
- Cancellation and reconciliation API actions are implemented, but the old
  cancellation endpoint was described as a mock and neither flow is live-verified.
- Beem SMS is sent when a control number is available; delivery depends on
  provider availability and configured credentials.

These limitations describe running code; they are not guarantees of gateway
compatibility or authentication.
