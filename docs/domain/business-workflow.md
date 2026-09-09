# Business Workflow

> How a customer's stones move through TGC-SYSTEM, end to end — the stages, who
> acts at each one, and how a stone's status changes along the way.
>
> This describes the **business process**, not the code. For the data model see
> the ERD in [`domain-questions.md`](domain-questions.md); for open decisions
> that affect this flow, see Parts B and C of that same file.
>
> Items marked **(assumption)** depend on a question not yet answered by the
> team — treat them as provisional.

---

## 1. The process at a glance

```
 ┌────────────┐   ┌──────────────┐   ┌──────────┐   ┌────────────┐   ┌──────────────┐
 │ RECEPTION  │──▶│ TYPE         │──▶│ BILLING  │──▶│ FINDINGS   │──▶│ CERTIFICATE  │
 │            │   │ IDENTIFY     │   │ & PAYMENT│   │ (examine)  │   │  & HANDOVER  │
 └────────────┘   └──────────────┘   └──────────┘   └────────────┘   └──────────────┘
   receptionist     gemmologist        accountant     gemmologist       receptionist
```

- An **Order** groups one or many **Stones** brought by one **Customer**.
- Each **Stone** flows through the pipeline **independently** — one stone may be
  certified while another in the same order is still awaiting findings.
- **Findings are recorded after payment.** The gemmologist first assigns only the
  stone's **type** (which fixes the price); the customer pays; then the full
  gemmological findings are recorded and the report is finalized.
- Billing happens once **per order**; certificates are issued **per stone**.

---

## 2. Roles (actors)

The four seeded roles (C5 ✅ resolved — see [permissions.md](../engineering/permissions.md)):

| Role | Responsible for |
| --- | --- |
| **Receptionist** | Registers customers, creates orders, logs stones, hands over finished certificates. |
| **Gemmologist** | Identifies each stone's type, then (after payment) records findings and finalizes the report. |
| **Accountant** | Generates bills, handles GePG, confirms payment. |
| **Administrator** | Manages reference data (lookups, prices) and users. |

---

## 3. Stage by stage

### Stage 1 — Reception
**Who:** Receptionist

1. Register the **Customer**.
2. Create an **Order** for the visit, recording only **how many stones** the
   customer submitted (`stone_count`).

The receptionist does **not** examine or measure stones — no type, weight, or
other property is recorded here. Individual stone records are created later, at
identification.

**Result:** an Order with a `stone_count`; no `Stone` records yet.

---

### Stage 2 — Type identification
**Who:** Gemmologist

1. Take a physical stone and **register it** on the order (`add_stone`),
   assigning only its **stone type**. This creates the `Stone` record
   (`received`) and, via the type, **fixes the price**. The system caps
   registrations at the order's `stone_count`.
2. Full gemmological findings are **not** recorded yet — they come after payment
   (Stage 4).

**Result:** each submitted stone becomes a `Stone` record with a known type (and
therefore a known price); weight and findings are still blank.

---

### Stage 3 — Billing & Payment
**Who:** Accountant

1. Once an order's stones are typed, generate **one Bill for the Order**.
2. The bill has a **line item per stone**, priced by a **flat rate per stone
   type** (weight does not change the price). The charge is **frozen onto the line
   item** at billing time, so later price-list changes never alter an issued bill.
3. Submit the bill to **GePG**, which returns a **control number**.
4. The customer pays; payment is confirmed via the GePG callback (a dev
   "simulate payment" path exists for local testing).

> **(assumption)** Partial payments and bill cancellation/reissue are open
> question C2.

**Result:** the order is billed and, once settled, marked paid — which unlocks
findings.

---

### Stage 4 — Findings
**Who:** Gemmologist

1. For each **paid** stone, record the full findings on its **Identification
   Report** — weight, color (grouped GIA-style list), nature, species, variety,
   origin, treatment, shape/cut, transparency, optic character, dimensions,
   refractive index, specific gravity, and instrument readings (all chosen from
   admin-managed reference lists).
2. **Finalize** the report, which locks it against further edits.

> **(assumption)** Whether a finalized report can still be edited is open
> question C4.

**Result:** each paid stone has one finalized identification report; status
advances toward certification.

---

### Stage 5 — Certificate & Handover
**Who:** Receptionist (issue/handover), system (verification)

1. A **Certificate is issued per stone**, carrying its identification results.
2. Each certificate has a **QR code** linking to a public verification page.
3. The customer collects the certified stones; handover is recorded.

> **(assumption)** Whether payment must be **complete before** a certificate is
> issued is open question B4. Certificate re-issuance and revocation are C3.

**Result:** each stone is certified and, once collected, closed out.

---

## 4. Stone status lifecycle

Each stone carries its **own status** (a fixed set defined in code), and every
change is written to a **status-history audit trail** recording *who* moved it,
*from* which status, *to* which status, *when*, and an optional note.

The status list (B5 ✅ resolved):

```
received
   │
   ▼
under_identification
   │
   ▼
billed
   │
   ▼
paid
   │
   ▼
certified
   │
   ▼
ready_for_collection
   │
   ▼
collected

  side states:  on_hold   ·   cancelled
```

**Audit trail — every transition records:**

| Field | Example |
| --- | --- |
| Stone | Stone #A of Order ORD-2026-0042 |
| From status | `under_identification` |
| To status | `billed` |
| Changed by | gemmologist J. Doe |
| Changed at | 2026-08-27 14:05 |
| Note | "type identified: Ruby" |

---

## 5. Key business rules (confirmed)

1. **Reception records only a stone count** (`stone_count`); stones are created
   later, at type identification, one record per physical stone.
2. A **report is produced per stone**, and **findings are recorded after
   payment** (type first → pay → findings → finalize).
3. Reference data (colors, species, treatments, prices, …) is **admin-managed**;
   staff select from fixed lists, not free text.
4. **One Bill per Order** — the customer pays once for the whole batch.
5. Pricing is a **flat rate per stone type** — weight does not change the price.
6. A **certificate is issued per stone**.
7. Each **stone moves independently** through the pipeline.
8. Workflow **stages are fixed** (defined in code, not staff-editable).
9. A **status audit trail is mandatory** — every transition is logged.

*(These are the confirmed decisions — Part A of `domain-questions.md`.)*

---

## 6. Open points that change this workflow

Answers to these will update the stages above. See `domain-questions.md`.

| Ref | Question | Affects |
| --- | --- | --- |
| B4 | Must a bill be paid before certification? | Stages 3→5 |
| C2 | Partial payments, bill cancellation? | Stage 3 |
| C3 | Certificate re-issue / revocation? | Stage 5 |
| C4 | Finalized report editable? | Stage 4 |
| C6 | Human-readable order/certificate numbers? | Stages 1, 5 |

*(Resolved and no longer open: B1/B6 production removed · B2 flat pricing ·
B3 weight unit ct/g · B5 status list · C5 roles.)*
```
