# GePG adapter overview

## Code map

| Module | Responsibility |
| --- | --- |
| [`gateways/gepg.py`](../../apps/billing/gateways/gepg.py) | XML construction/parsing and outbound HTTP |
| [`gateways/signing.py`](../../apps/billing/gateways/signing.py) | Optional PKCS#12 signing |
| [`services/bill.py`](../../apps/billing/services/bill.py) | Local bill creation, submission, retries, callbacks |
| [`services/identification.py`](../../apps/billing/services/identification.py) | Stone registration and automatic billing handoff |
| [`services/payment.py`](../../apps/billing/services/payment.py) | Payment persistence and settlement |
| [`webhooks.py`](../../apps/billing/webhooks.py) | Plain Django POST views returning XML |

One outbound endpoint and two inbound endpoints are wired:

```text
POST <GEPG_BILL_CREATE_URL>        billSubReq -> billSubRes or billSubReqAck
POST /gepg/bill/response/         billSubRes -> billSubResAck
POST /gepg/payments/notification/ pmtSpNtfReq -> pmtSpNtfReqAck
```

Callbacks are outside `/api/v1/` so their registered URLs remain stable across
API versions. They are CSRF-exempt and do not require JWT authentication.
Handled service failures return acknowledgement code `7102`; success uses
`7101`. XML replies use `text/xml; charset=utf-8`. Unhandled exceptions and
unsupported methods are not guaranteed to return acknowledgement XML.

## Configuration

Values and defaults live in `config/settings/base.py` and `.env.example`:

- `GEPG_BILL_CREATE_URL`: destination for submissions (30-second HTTP timeout).
- `GEPG_SP_GRP_CODE`, `GEPG_SYS_CODE`, `GEPG_SP_CODE`, `GEPG_SUB_SP_CODE`,
  `GEPG_COLL_CENT_CODE`, `GEPG_GFS_CODE`: identifiers used in XML and headers.
- `GEPG_BILL_EXPIRY_DAYS`: local expiry interval, default 365 days.
- `GEPG_USE_DIGITAL_SIGNATURE`: optional signing, default false.
- `GEPG_PRIVATE_KEY_PATH`, `GEPG_CERTIFICATE_PASSWORD`: PKCS#12 key and password.
- `GEPG_SIMULATE`: bypass outbound HTTP, default false in settings and true in
  the development example file.
- `AUTO_BILL_AFTER_IDENTIFICATION`: automatic billing on final registration,
  default false.

`GEPG_ACK_SUCCESS_CODES` contains `7101` and `7241` for submission acknowledgements.
The adapter uses settings for gateway identifiers; attaching a `ServiceProvider`
to a bill does not override those values.

## Signing

`sign_content()` signs the UTF-8 content inside `<Gepg>`, excluding the signature
element, with RSA PKCS#1 v1.5 and SHA-256, then base64-encodes it. The private key
is cached in-process. `sign_if_enabled()` is used for submissions and replies.
When disabled, XML retains `SignatureGoesHere`; it is not a valid signature.
See [current limitations](README.md#current-limitations) before relying on signing.
