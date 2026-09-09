# GePG integration

The Tanzanian government payment gateway. A bill is submitted for a **control
number**, the customer pays that number at any bank or mobile wallet, and GePG
tells us asynchronously. There is no manual payment entry anywhere in the system.

## Read these in order

| Doc | Covers |
| --- | --- |
| [00 Overview](00_GEPG_INTEGRATION_OVERVIEW.md) | Configuration, architecture, message catalogue |
| [01 Bill submission](01_BILL_SUBMISSION.md) | `billSubReq` - getting a control number |
| [02 Payment notification](02_PAYMENT_NOTIFICATION.md) | `pmtSpNtfReq` - the callback that settles a bill |
| [03 Bill cancellation](03_BILL_CANCELLATION.md) | `billCancReq` - **not implemented** |
| [04 Reconciliation](04_RECONCILIATION.md) | `sucSpPmtReq` - **not implemented** |
| [05 SMS](05_SMS_INTEGRATION.md) | Beem Africa - **not implemented** |

## About the file paths in these documents

**They are provenance, not a map of this codebase.** These documents were written
against the legacy TGC-MIFUMO system, and quote paths like
`/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py`. They are kept
verbatim because the *protocol* they describe - the XML shapes, the status codes,
the signing scheme, the acknowledgement rules - cannot be re-derived from our
code, and getting a digit wrong against a government gateway is expensive.

Where a document names a legacy module, this is where the same job is done here:

| In these documents | In this codebase |
| --- | --- |
| `billing_system_app/services.py` | [`apps/billing/services/`](../../apps/billing/services/) |
| `gepg_service.py` | [`apps/billing/gateways/gepg.py`](../../apps/billing/gateways/gepg.py) |
| `crypto_utils.py` | [`apps/billing/gateways/signing.py`](../../apps/billing/gateways/signing.py) |
| `views/payment_api.py` | [`apps/billing/webhooks.py`](../../apps/billing/webhooks.py) |
| `billing_system_app/models.py` | [`apps/billing/models/`](../../apps/billing/models/) |
| `sms_service.py` | nothing - SMS is not implemented |

## What is actually wired up

Two outbound calls and two inbound callbacks:

```
POST  <GEPG_BILL_CREATE_URL>          billSubReq   -> control number
POST  /gepg/payments/notification/    pmtSpNtfReq  -> 7101 / 7102 ack
POST  /gepg/bill/response/            billSubRes   -> ack (late control number)
```

The callbacks sit **outside** `/api/v1/` because their URLs are registered with
GePG out of band and must survive an API version bump. They are plain Django
views, unauthenticated and CSRF-exempt, and they answer in XML on every path
including failure - see the module docstring in
[`apps/billing/webhooks.py`](../../apps/billing/webhooks.py) for the full
reasoning.

## Working offline

Set `GEPG_SIMULATE=True` in `.env`. Bill submission then skips the network and
returns a plausible control number, and:

```bash
uv run python manage.py simulate_payment BILL-2026-0004
```

settles a bill by feeding a fake notification through the **real** handler, so
the whole path - parse, record, settle, transition the stones - is exercised.

## Gaps to be aware of

These are carried over from the system being ported, and none of them is closed:

1. **No inbound signature verification.** `GEPG_PUBLIC_CERT_PATH` is configured
   but never read. The notification endpoint is public, unauthenticated and
   CSRF-exempt, so a forged `pmtSpNtfReq` will mark a bill paid. This is the
   most serious open item in the project.
2. **Signing fails open.** A missing or unreadable PKCS#12 key logs an error and
   sends the payload **unsigned** rather than refusing.
3. **No retry.** A network failure leaves a local bill with no control number and
   no path forward - no re-submit, no queue, no dead letter.
4. **No cancellation or reconciliation.** `GEPG_BILL_CANCEL_URL` and
   `GEPG_RECONCILIATION_URL` are configured but nothing reads them; documents 03
   and 04 describe the protocol, not an implementation.
5. **No SMS.** Document 05 describes Beem Africa; no code calls it.
