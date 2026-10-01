# GePG Integration — Overview

GePG is the Tanzanian government's electronic payment gateway. The lab does not
take money directly: a bill is submitted to GePG, which issues a **control
number**, the customer pays that number at any bank or mobile wallet, and GePG
tells us afterwards. There is no manual payment entry anywhere in the system.

This document describes what is configured and what is wired up. The individual
message contracts are in the numbered documents beside it.

| Document | Message | State |
| --- | --- | --- |
| [01 Bill submission](01_BILL_SUBMISSION.md) | `billSubReq` | Implemented |
| [02 Payment notification](02_PAYMENT_NOTIFICATION.md) | `pmtSpNtfReq` | Implemented |
| [03 Bill cancellation](03_BILL_CANCELLATION.md) | `billCanclReq` | Specification only |
| [04 Reconciliation](04_RECONCILIATION.md) | `sucSpPmtReq` | Specification only |
| [05 SMS notifications](05_SMS_INTEGRATION.md) | Beem Africa | Specification only |

---

## What is wired up

Two outbound calls and two inbound callbacks. That is the whole integration.

```
outbound   POST <GEPG_BILL_CREATE_URL>         billSubReq   → control number
inbound    POST /gepg/bill/response/           billSubRes   → late control number
inbound    POST /gepg/payments/notification/   pmtSpNtfReq  → settles the bill
```

A bill is raised per **order**, not per stone, and is priced from the stone
**category** of each stone on it.

Both callbacks sit **outside** `/api/v1/`, because their URLs are registered
with GePG out of band and have to survive an API version bump. They are plain
Django views — unauthenticated, CSRF-exempt — and they answer in XML on every
path, including failure. The reasoning is in the module docstring of
[`apps/billing/webhooks.py`](../../apps/billing/webhooks.py).

### Where the code lives

| Concern | Module |
| --- | --- |
| Bill and payment services | [`apps/billing/services/`](../../apps/billing/services/) |
| XML building and parsing | [`apps/billing/gateways/gepg.py`](../../apps/billing/gateways/gepg.py) |
| PKCS#12 loading and signing | [`apps/billing/gateways/signing.py`](../../apps/billing/gateways/signing.py) |
| The two inbound callbacks | [`apps/billing/webhooks.py`](../../apps/billing/webhooks.py) |
| Models | [`apps/billing/models/`](../../apps/billing/models/) |
| Development simulation | [`apps/billing/dev.py`](../../apps/billing/dev.py) |

---

## Configuration

All values come from the environment. Every credential defaults to an empty
string, so a misconfigured deployment fails visibly rather than talking to the
wrong gateway.

### Endpoints

```
GEPG_BILL_CREATE_URL=https://<gepg-host>/api/bill/20/submission
GEPG_BILL_CANCEL_URL=https://<gepg-host>/api/bill/20/cancellation      # read by nothing
GEPG_RECONCILIATION_URL=https://<gepg-host>/api/reconciliation/20/request  # read by nothing
```

The last two are configured but **not used** — the features they belong to are
documents 03 and 04, which are specifications.

### Identity

```
GEPG_SP_GRP_CODE=<set-in-.env>        service provider group
GEPG_SYS_CODE=<set-in-.env>           the system registered with GePG
GEPG_SP_CODE=<set-in-.env>            service provider
GEPG_SUB_SP_CODE=<set-in-.env>        sub service provider
GEPG_COLL_CENT_CODE=<set-in-.env>     collection centre
GEPG_GFS_CODE=<set-in-.env>           the revenue code every bill item carries
```

### Signing

```
GEPG_USE_DIGITAL_SIGNATURE=False                    # opt-in, off by default
GEPG_PRIVATE_KEY_PATH=certificates/private.pfx      # PKCS#12, signs outbound
GEPG_CERTIFICATE_PASSWORD=<set-in-.env>             # no default; a blank one would
                                                    # let an unsigned payload through
GEPG_PUBLIC_CERT_PATH=certificates/public.pfx       # read by nothing — see Gaps
```

### Behaviour

```
GEPG_BILL_EXPIRY_DAYS=365      how long a control number stays payable
GEPG_SIMULATE=False            skip the network; see "Working offline"
```

---

## What actually happens

### Raising a bill

`generate_bill_for_order()` prices each stone from its category, freezes the
charge onto the line item, allocates a `BILL-YYYY-NNNN` number, and submits.

GePG can answer in three ways:

| Answer | What happens |
| --- | --- |
| Control number in `billSubRes` | Stored immediately |
| Acknowledgement only (`7101`/`7241`) | The number arrives later on the response callback |
| The literal `PENDING` | **Not stored.** `control_number` stays empty |

That last case is deliberate. The unique constraint on control numbers excludes
blanks, so an empty string is a legitimate "not yet"; storing `"PENDING"` would
occupy the slot the real number needs and make every un-numbered bill collide
with every other.

### Receiving a payment

The notification handler is **idempotent on `trx_id`**: the payment row is
fetched or created by transaction id, and the bill's status is recomputed only
when a genuinely new payment lands. GePG redelivers, so this matters.

Settlement compares the sum of payments against the bill total:

- covered in full → `paid`, and every stone on the order transitions to `paid`
- covered in part → `partially_paid`, and nothing moves

The endpoint answers **HTTP 200 with an XML acknowledgement on every path**,
including a parse failure — where it returns code `7102`. Returning a 4xx would
make GePG treat the delivery as failed and send it again, which is exactly what
the idempotency above exists to survive rather than invite.

XML is parsed with `defusedxml`, not the standard library. The endpoint is
public, and `xml.etree.ElementTree` is documented as unsafe against hostile
input.

---

## Working offline

Set `GEPG_SIMULATE=True`. Bill submission then skips the network and returns a
plausible control number.

With `DEBUG` on as well, the Bills screen grows a **Simulate payment** action.
It settles a bill by feeding a synthetic notification through the **real**
handler, so the whole path — parse, record, settle, transition the stones — runs
exactly as it would in production. It takes an amount, so a part-paid bill can
be produced as well as a settled one; leaving it blank pays the outstanding
balance.

Behind it: `POST /api/v1/bills/{id}/simulate-payment/`, which answers **404**
unless the server has **both** `DEBUG` and `GEPG_SIMULATE` on. A 404 rather than
a 403, so a production deployment does not advertise that the endpoint exists.

---

## Data model

The columns that matter to this integration, on
[`apps/billing/models/bill.py`](../../apps/billing/models/bill.py):

### `Bill`

| Column | Notes |
| --- | --- |
| `bill_number` | `BILL-YYYY-NNNN`, allocated locally |
| `control_number` | Issued by GePG; empty until it arrives |
| `order` | One-to-one — one bill per order |
| `total_amount` | Sum of the line items |
| `status` | `pending`, `partially_paid`, `paid`, `cancelled`, `expired` |
| `bill_type`, `pay_type` | Small integers, both defaulting to `1` |
| `status_code`, `status_desc` | The raw gateway strings from submission |
| `gepg_submitted_at` | When it went out |

`cancelled` and `expired` are declared but never written — see document 03.

### `Payment`

| Column | Notes |
| --- | --- |
| `bill` | Foreign key |
| `trx_id` | GePG's transaction id — the idempotency key |
| `gepg_bill_id` | The bill id as GePG knows it |
| `paid_amount`, `bill_amount` | Decimals |
| `trx_dt_tm` | When the customer paid |
| `pyr_name`, `pyr_cell_num`, `pyr_email` | Who paid |

`trx_id` carries a **partial** unique constraint that excludes blanks and
soft-deleted rows, not `unique=True` — the same rule every natural key in the
project follows.

---

## Gaps

None of these is closed. They are listed roughly in order of how much they
would cost to be wrong about.

1. **No inbound signature verification.** `GEPG_PUBLIC_CERT_PATH` is configured
   but never read. The notification endpoint is public, unauthenticated and
   CSRF-exempt, so a forged `pmtSpNtfReq` will mark a bill paid. This is the
   most serious open item in the project.
2. **Signing fails open.** A missing or unreadable PKCS#12 key logs an error and
   sends the payload **unsigned** rather than refusing. Combined with the
   default being off, assume outbound messages are currently unsigned.
3. **No retry.** A network failure leaves a bill with no control number and no
   path forward — no re-submit, no queue, no dead letter. The gateway call logs
   and returns; nothing picks it back up.
4. **No cancellation, no reconciliation, no SMS.** Documents 03, 04 and 05
   describe protocols, not implementations.
5. **No expiry enforcement.** `GEPG_BILL_EXPIRY_DAYS` is sent to GePG, but
   nothing locally moves a bill to `expired` when the date passes.
