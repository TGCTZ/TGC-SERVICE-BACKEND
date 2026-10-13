# GePG adapter overview

## Code map

| Module | Responsibility |
| --- | --- |
| [`gateways/gepg.py`](../../apps/billing/gateways/gepg.py) | XML construction/parsing and outbound HTTP |
| [`gateways/signing.py`](../../apps/billing/gateways/signing.py) | Outbound signing and inbound signature verification |
| [`gepg_transport.py`](../../apps/billing/gepg_transport.py) | Persisted outbound requests and bounded transport retries |
| [`tasks.py`](../../apps/billing/tasks.py) | Celery callback processing and inbox/outbox recovery |
| [`services/bill.py`](../../apps/billing/services/bill.py) | Local bill creation, submission, retries, callbacks |
| [`services/identification.py`](../../apps/billing/services/identification.py) | Stone registration and automatic billing handoff |
| [`services/payment.py`](../../apps/billing/services/payment.py) | Payment persistence and settlement |
| [`services/gepg_operations.py`](../../apps/billing/services/gepg_operations.py) | Cancellation, reconciliation, and their callbacks |
| [`webhooks.py`](../../apps/billing/webhooks.py) | Plain Django POST views returning XML |

Bill creation, cancellation, and reconciliation each use their configured
outbound endpoint. The four legacy callback paths are wired alongside the
newer `/gepg/` paths:

```text
POST <GEPG_BILL_CREATE_URL>        billSubReq -> billSubRes or billSubReqAck
POST /gepg/bill/response/         billSubRes -> billSubResAck
POST /gepg/payments/notification/ pmtSpNtfReq -> pmtSpNtfReqAck
POST /gepg/bill/cancel-response/  billCanclRes acknowledgement
POST /gepg/reconciliation/response/ sucSpPmtRes acknowledgement
POST /billing/api/bill/cancel-response/       billCanclRes callback
POST /billing/reconciliation/response/        sucSpPmtRes callback
```

The old registered paths for payment and bill responses are also served at
`/billing/api/payments/notification/` and `/billing/api/bill/response/`.
Permission-checked actions are available at
`POST /api/v1/bills/{id}/cancel/` and
`POST /api/v1/reconciliations/request/`.

Callbacks are outside `/api/v1/` so their registered URLs remain stable across
API versions. They are CSRF-exempt and do not require JWT authentication.
Valid callbacks are signature-verified, persisted in the PostgreSQL inbox, and
queued before the endpoint returns `7101`. Invalid signatures receive `7303`;
invalid request data receives `7242`. A database or broker failure returns
HTTP 503 so GePG can redeliver. XML replies use `text/xml; charset=utf-8`.

## Configuration

Values and defaults live in `config/settings/base.py` and `.env.example`:

- `GEPG_BILL_CREATE_URL`: destination for submissions (30-second HTTP timeout).
- `GEPG_BILL_CANCEL_URL`, `GEPG_RECONCILIATION_URL`: outbound destinations for
  cancellation and daily reconciliation requests.
- `GEPG_SP_GRP_CODE`, `GEPG_SYS_CODE`, `GEPG_SP_CODE`, `GEPG_SUB_SP_CODE`,
  `GEPG_COLL_CENT_CODE`, `GEPG_GFS_CODE`: identifiers used in XML and headers.
- `GEPG_BILL_EXPIRY_DAYS`: local expiry interval, default 365 days.
- `GEPG_USE_DIGITAL_SIGNATURE`: outbound signing switch; enable in production.
- `GEPG_COM`, `GEPG_ALG`: registered values for the matching GePG HTTP headers.
- `GEPG_PRIVATE_KEY_PATH`, `GEPG_CERTIFICATE_PASSWORD`: PKCS#12 key path and its
  local encryption password.
- `GEPG_PUBLIC_CERT_PATH`, `GEPG_PUBLIC_CERTIFICATE_PASSWORD`: GePG public
  certificate for callback signature verification.
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`: Redis broker and result backend.
- `GEPG_RETRY_INITIAL_SECONDS`, `GEPG_RETRY_MAX_SECONDS`,
  `GEPG_RETRY_MAX_AGE_SECONDS`: outbound retry bounds; defaults are 60, 1800,
  and 86400 seconds.
- `BEEM_AFRICA_API_KEY`, `BEEM_AFRICA_SECRET_KEY`: credentials for control-number
  SMS delivery.
- `GEPG_SIMULATE`: bypass outbound HTTP; the settings and example-file defaults
  are false. Set true only for local offline development.
- `AUTO_BILL_AFTER_IDENTIFICATION`: automatic billing on final registration,
  default false.

Only `7101` is accepted as a successful bill-submission acknowledgement;
`7241` indicates an invalid session.
The adapter uses settings for gateway identifiers; attaching a `ServiceProvider`
to a bill does not override those values.

## Signing

`sign_content()` signs the UTF-8 content inside `<Gepg>`, excluding the signature
element, with RSA PKCS#1 v1.5 and SHA-256, then base64-encodes it. The private key
is cached in-process. `sign_if_enabled()` is used for submissions and replies.
When disabled in development, XML retains `SignatureGoesHere`; it is not valid
for live traffic. Production settings require signing keys and the registered
GePG public certificate, and callbacks are rejected unless their signature
verifies. See the [production setup](04_GEPG_PRODUCTION_SETUP.md).
