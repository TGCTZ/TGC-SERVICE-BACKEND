# Domain & Business Rules — Questions for the Team

> Purpose: pin down the business rules that drive the database design **before**
> models are written. Part A records decisions already made. Part B lists open
> questions that still need an answer. Part C raises questions we haven't
> discussed yet but the team should consider.
>
> Please review Part B and Part C and fill in answers. Each answer directly
> shapes the database schema.

> **Status of the assumptions.** Several provisional defaults are now settled in
> code; the rest still ride on the defaults below pending team answers.
>
> - **B1 / B6 ✅** — **no production module** in the current build; a stone goes
>   type-identification → billing → findings → certificate.
> - **B2 ✅** — pricing is **flat per stone type** (`StoneType.price`); weight
>   does not change the price.
> - **B3 ✅** — weight unit is **carat/gram** (`WeightUnit`); no `SiUnit`.
> - **B5 ✅** — the `StoneStatus` list is settled (no `in_production`).
> - **C5 ✅** — four roles seeded (receptionist, gemmologist, accountant,
>   administrator).
> - **B4** — a certificate can be issued **only after the bill is fully paid**
>   (still provisional).
> - **C2** — **partial payments allowed**; bill is `paid` once payments cover the
>   total, else `partially_paid` (still provisional).
> - **C3** — certificates **can be revoked** (still provisional).
> - **C4** — a **finalized** report is **locked** (no further edits).
> - **C6** — reference formats: `ORD-YYYY-NNNN`, `RPT-YYYY-NNNN`,
>   `BILL-YYYY-NNNN`, `CERT-YYYY-NNNN` (per-year sequence).

---

## The workflow (shared understanding)

```
Customer brings stones
      ↓
RECEPTION       → an Order is created, containing one or more Stones
      ↓
TYPE IDENTIFY   → a gemmologist assigns each stone's type (fixes the price)
      ↓
BILLING         → one Bill per Order; GePG control number; customer pays
      ↓
FINDINGS        → after payment, the gemmologist records + finalizes the report
      ↓
CERTIFICATE     → a certificate is issued per stone (with QR verification)
```

---

## Part A — Decisions already made ✅

| # | Question | Decision |
| --- | --- | --- |
| A1 | Does an order contain one stone or many? | **One or a batch of many stones**, all under a single order. |
| A2 | Is a gemmological report produced per stone or per order? | **Per stone** — each stone gets its own identification report. |
| A3 | Is the reference data (colors, species, treatments, etc.) fixed or user-editable during data entry? | **Stable, admin-managed lookup lists** — staff choose from dropdowns; they are not added ad hoc during data entry. |
| A4 | Is billing per order or per stone? | **One Bill per Order** — the customer pays once for the whole batch. |
| A5 | Is a certificate issued per order or per stone? | **Per stone** — each stone gets its own certificate and QR verification. |
| A6 | What determines a stone's price? | **Stone type only** — a flat price per type (weight does not affect it). *(Refined from the original "type and weight" — see B2.)* |
| A7 | Does each stone carry its own status, or does the whole order move together? | **Each stone has its own status** and progresses independently through the pipeline. |
| A8 | Are the workflow stages fixed or editable by staff? | **Fixed stages defined in code** — they rarely change; developers manage them. |
| A9 | Is a status audit trail needed? | **Yes — a full audit trail is a must** ("who moved this stone to which stage, and when"). |
| A10 | Is production one model or three separate ones? | ~~One Production model with a `type` field.~~ **Superseded — the production module is not part of the current build** (see B1/B6). |

---

## Part B — Open questions (need answers) ❓

### B1. Can a stone go through **multiple** production steps?
Can one stone be processed more than once — e.g. lapidary **and then** carving —
or is it strictly **one production step per stone**?
- *If multiple:* a Stone can have many Production records.
- *If one:* a Stone has at most one Production record.

**Answer:** ✅ Moot — the **production module was removed**; there is no Production
record. A stone goes type-identification → billing → findings → certificate.

---

### B2. Is pricing a **flat rate** or **tiered by weight**?

**Answer:** ✅ **Flat per stone type.** Each `StoneType` carries its own `price`;
weight is recorded but does not change the amount charged.

> The full-stack system kept this on a separate `StonePrice` table. Here it is a
> column on `StoneType`, which means the permission to set a price is the
> permission to edit the stone catalogue - see `docs/engineering/permissions.md`.

---

### B3. What is the unit of weight — **carats or grams** (or both)?

**Answer:** ✅ **Carat (default) or gram** — the `WeightUnit` enum (`ct`/`g`).
There is no `SiUnit` table.

---

### B4. Can a stone be **billed but not yet certified**, and vice versa?
Confirm the ordering rule between payment and certification:
- Must a Bill be **fully paid** before a certificate is issued?
- Or can certificates be issued independently of payment status?

**Answer:**

---

### B5. What are the exact **workflow stages** (the fixed status list)?
We need the definitive, ordered list of stone statuses to define in code.
Draft based on the workflow — **please correct/complete**:

```
1. received            (logged at reception)
2. under_identification
3. billed
4. paid
5. certified
6. ready_for_collection
7. collected
   + cancelled / on_hold  (side states)
```

**Answer / corrections:** ✅ The list above is the implemented `StoneStatus`
(no `in_production`).

---

### B6. Can a stone **skip** stages?

**Answer:** ✅ Moot — with no production stage, the pipeline is
type-identification → billing → findings → certificate. `on_hold` / `cancelled`
remain available side states.

---

## Part C — Questions we haven't discussed (please consider) 🔎

These weren't raised yet but affect the schema or business logic. Please weigh in.

### C1. Customer identity
What identifies a customer — name + phone, a national/tax ID, a company?
Can the **same customer** return for multiple orders (so we keep a customer
record), or is customer info captured **fresh per order**?

**Answer:**

---

### C2. GePG billing specifics
- Does every Bill go through GePG, or are there other payment methods?
- What happens on **partial payment** — is that a valid state, or must bills be
  paid in full?
- Can a Bill be **cancelled or reissued** after a control number is generated?

**Answer:**

---

### C3. Certificate re-issuance & revocation
- Can a certificate be **re-issued** (e.g. lost copy, correction)?
- Can a certificate be **revoked/invalidated** after issue? If so, the public QR
  verification must reflect that.

**Answer:**

---

### C4. Editing after the fact
Once a stone is billed or certified, can its identification report still be
**edited**? If reports are locked at some stage, we need to enforce that in the
model.

**Answer:**

---

### C5. Who can do what (roles)
The system has a custom user model. What **roles** exist (receptionist,
gemmologist, production staff, accountant, admin…), and which stages can each
role act on? This drives the permissions layer.

**Decided ✅:** roles are **Django Groups** — receptionist, gemmologist,
accountant, administrator — seeded by `python manage.py setup_roles`. Action-level
custom permissions (`finalize_report`, `generate_bill`, `issue_certificate`, …)
are defined on the models. The role→permission mapping lives in
`apps/accounts/roles.py`; see
[`../engineering/permissions.md`](../engineering/permissions.md).

**Still needed from the team:** confirm/adjust which actions each role may
perform (edit `ROLE_PERMISSIONS`).

**Answer (confirmations / changes to the mapping):**

---

### C6. Order / stone identifiers
- Does an Order need a **human-readable reference number** (e.g. `ORD-2026-0042`)?
  What format?
- Does each Stone/certificate need its own external-facing number?

**Answer:**

---

### C7. Data retention & history
Beyond the status audit trail, does the business need to keep a history of
**edits** to reports or bills (who changed a value and when), or is the status
trail sufficient?

**Answer:**

---

## Current draft data model (for reference)

This is the schema implied by the decisions in Part A. It will change based on
Part B and Part C answers.

```
Customer 1──< Order 1──1 Bill 1──< BillItem >──1 Stone
                 │                                  │
                 └──< Stone ───────────────────────┘
                        │  status (fixed enum) + StatusHistory (audit)
                        │
      ┌─────────────────┴──────────────────┐
      │ 1                                   │ 1
 IdentificationReport                  Certificate
 (per stone)                           (per stone)
      │
      └─ FKs → gems lookups: StoneType, Species, Variety, Color, Origin,
               ShapeCut, Instrument
         + enums: NatureType, Transparency, Treatment, OpticCharacter
```
