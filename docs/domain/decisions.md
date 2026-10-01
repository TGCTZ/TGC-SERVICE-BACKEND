# Business decisions

The business rules that shape the system: what was decided, why, and where it
lives in code. Read this before changing behaviour that a rule below covers -
if the rule itself needs to change, change it here in the same pull request.

Decisions are **settled** (built, and confirmed by the lab) or **provisional**
(built on a sensible default, awaiting the lab's confirmation). Questions the
lab has not answered yet are at the end.

## The pipeline

```
RECEPTION    an Order is created for one visit, with the number of stones handed in
    ↓
IDENTIFY     a gemmologist types each stone - which fixes its price
    ↓
BILLING      one Bill per Order, a GePG control number, the customer pays
    ↓
FINDINGS     after payment the gemmologist records and finalizes the report
    ↓
CERTIFICATE  one certificate per stone, downloadable as a PDF
```

The full walk-through, with statuses and roles, is in
[Business workflow](business-workflow.md).

## Settled

| Rule | Why | In code |
| --- | --- | --- |
| An order holds one or many stones from one visit | Customers bring parcels; one receipt, one bill | `Order`, `Order.stone_count` |
| Reception records only how many stones arrived; a `Stone` row is created when the bench identifies it | Typing a stone is gemmological work, not reception's | `orders.services.stone.add_stone` |
| Each stone has its own status and moves independently | Stones from one parcel are finished at different times | `Stone.status`, `StoneStatus` |
| The status list is fixed in code: received, under identification, billed, paid, certified, ready for collection, collected, plus on hold and cancelled | Stages rarely change, and code depends on them | `apps/gems/enums.py` |
| Every status change is recorded - who, when, from what to what | The lab must be able to answer "who moved this stone" | `StatusHistory` |
| Every write is audit-logged | Edits to reports, bills and records must be traceable | `django-auditlog`, `apps/core/audit.py` |
| One bill per order | The customer pays once for the whole visit | `Bill.order` (one-to-one) |
| Price is a flat fee per stone category, reached through the stone's type; weight does not change it | The lab charges by class of work, and a new type is priced the moment it exists | `StoneCategory.price`, `preview_bill_for_order` |
| Weight is in carats (default) or grams | The two units the lab uses | `WeightUnit` |
| One identification report per stone | Findings are per stone | `IdentificationReport.stone` |
| A finalized report is locked | A certificate must not describe findings that later change | `finalize_report` |
| One certificate per stone, printed from a snapshot of the report | A certificate must say what it said on the day it was issued | `Certificate.*_snapshot` |
| Certificates are revoked, never deleted; a revoked one still downloads, watermarked | Whoever holds the paper must be able to reconcile it | `revoke_certificate` |
| Reference data (colours, species, origins…) is admin-managed lookup lists | Staff pick from lists; free text drifts | `apps/gems` |
| A customer is a lasting record, unique by phone | Customers return; reception finds them rather than re-registering | `Customer` |
| Reference numbers read `PREFIX-<yy><yy>-NNNNN` over the financial year (July-June), restarting each year: `ORD-`, `BILL-`, `CERT-`, and `TGC-` for reports | One format everywhere, aligned with the government financial year | `apps/core/services.py` |
| Six roles: superadmin, admin, manager, receptionist, gemmologist, accountant | Four stations plus two roles that run the system | `apps/users/roles.py` |
| No production module: identification → billing → findings → certificate | Removed from scope; stages cannot be skipped | - |

## Recent decisions

| Date | Rule | Why | In code |
| --- | --- | --- | --- |
| 2026-09-25 | Management statistics are a separate permission, granted to manager (and above) | They put revenue beside workload; reading bills does not clear someone to see the lab's whole financial picture | `analytics.view_statistics` |
| 2026-09-25 | Roles form a hierarchy: everyone manages only the roles and people ranked below them, and does not see those above | Stops self-promotion and managers editing admins; only a superadmin manages admins | `ROLE_RANKS`, `apps/users/services/roles.py` |
| 2026-09-25 | A customer's region is one of Tanzania's 31 regions | Free text could not be counted or searched reliably | `Region`, `apps/gems/regions.py` |
| 2026-09-25 | No self-registration: staff create accounts from an email and a role | Every account belongs to someone the lab chose | `create_user_account` |
| 2026-09-25 | New accounts get a random temporary password, not a shared default, and must set a password and complete their profile before using the system | A shared default lets anyone who knows a new colleague's email take the account first | `apps/users/services/accounts.py`, `apps/users/authentication.py` |
| 2026-09-25 | Every user's country is Tanzania; new accounts start Active | The lab's staff are in Tanzania | `create_user_account` |

## Provisional

Built on these defaults; the lab has not confirmed them.

| Rule | In code |
| --- | --- |
| A certificate is issued only after the bill is fully paid | the certification worklist filters on `BillStatus.PAID` |
| Partial payments are allowed: a bill is `partially_paid` until payments cover the total | `process_payment_notification` |
| The per-role list of actions in `ROLE_PERMISSIONS` | `apps/users/roles.py` |

## Open questions

- **Other ways to pay.** Does every bill go through GePG, or can the lab take cash
  or another channel?
- **Cancelling or reissuing a bill** after its control number is issued - allowed,
  and by whom? (`BillStatus.CANCELLED` exists; nothing sets it.)
- **Re-issuing a certificate** for a lost copy or a correction - a new number, or
  the old one? (`CertificateStatus.REISSUED` exists; nothing sets it.)
- **How long records are kept**, including the audit log.

## Data model

```
Customer 1──< Order 1──1 Bill 1──< BillItem >──1 Stone
                 │                                  │
                 └──< Stone ────────────────────────┘
                        │  status + StatusHistory
                        │
      ┌─────────────────┴──────────────────┐
      │ 1                                  │ 1
 IdentificationReport                 Certificate
      │                                (snapshot of the report)
      └─ lookups: StoneType, Species, Variety, Color, Origin, ShapeCut, Instrument
         enums: NatureType, Transparency, Treatment, OpticCharacter
```
