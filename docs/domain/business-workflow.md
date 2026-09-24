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
 ┌────────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐
 │ RECEPTION  │──▶│ IDENTIFY     │──▶│ BILLING  │──▶│ FINDINGS     │──▶│ CERTIFICATE  │
 │            │   │ (type→price) │   │ & PAYMENT│   │ (examine)    │   │  & HANDOVER  │
 └────────────┘   └──────────────┘   └──────────┘   └──────────────┘   └──────────────┘
   receptionist     gemmologist        accountant      gemmologist       receptionist
```

- An **Order** groups one or many **Stones** brought by one **Customer**.
- Each **Stone** flows through the pipeline **independently** — one stone may be
  certified while another in the same order is still awaiting identification.
- **The bench works in two stages, split by payment.** *Identification* assigns
  only the stone's **type**, which fixes the price; the customer pays; then the
  *findings* record the complete gemmological observations and the report is
  finalized. Both stages are the gemmologist's.
- Billing happens once **per order**; certificates are issued **per stone**.

---

## 2. Roles (actors)

The four seeded roles (C5 ✅ resolved — see [permissions.md](../engineering/permissions.md)):

| Role | Responsible for |
| --- | --- |
| **Receptionist** | Registers customers, creates orders, hands over finished certificates. Does **not** identify stones. |
| **Gemmologist** | Identification (the type, which fixes the price), then after payment the findings, and finalizes the report. |
| **Accountant** | Generates bills, handles GePG, confirms payment. |
| **Administrator** | Manages reference data (lookups, prices) and users. |

---

## 3. Stage by stage

### Stage 1 — Reception
**Who:** Receptionist

1. Create an **Order** for the visit, recording only **how many stones** the
   customer submitted (`stone_count`).
2. The **Customer** is chosen or registered *within* that same step: the
   receptionist searches by name or phone, picks the record if the customer has
   been here before, and fills in their details only if they have not. A
   customer is never registered on their own — they exist because an order is
   being received.

The receptionist does **not** examine or measure stones — no type, weight, or
other property is recorded here. Individual stone records are created later, at
identification.

**Result:** an Order with a `stone_count`; no `Stone` records yet.

---

### Stage 2 — Identification
**Who:** Gemmologist

1. Take a physical stone and **identify its type**
   (`POST /orders/{id}/stones/`). This creates the `Stone` record (`received`)
   and, via the type, **fixes the price**. The system caps this at the order's
   `stone_count`.
2. A type can be **corrected** (`PUT /stones/{id}/`) until the order is
   billed. Billing is what freezes the price onto the bill, so from then on the
   type is locked (`RETYPEABLE_STATUSES` in `apps/orders/services/stone.py`).
3. The **findings** is **not** recorded yet — it comes after payment
   (Stage 4).

**Result:** each submitted stone becomes a `Stone` record with a known type (and
therefore a known price); weight and the full findings are still blank.

---

### Stage 3 — Billing & Payment
**Who:** Accountant

1. Once an order's stones are typed, generate **one Bill for the Order**.
2. The bill has a **line item per stone**, priced by a **flat fee per stone
   category** — reached through the stone's type, since the fee is a property of
   the class of work rather than the species (weight does not change it). The
   charge is **frozen onto the line item** at billing time, so later price-list
   changes never alter an issued bill.

   Because the fee is not on the stone type, a total cannot be worked out from a
   stone's type alone. `preview_bill_for_order()` exists so the screen that asks
   for a bill shows the same figure the bill will carry.
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
   origin, treatment, shape/cut, transparency, optic character, refractive
   index, specific gravity, and which instruments were used (all chosen from
   admin-managed reference lists).
2. **Finalize** the report, which locks it against further edits.

> **(assumption)** Whether a finalized report can still be edited is open
> question C4.

**Result:** each paid stone has one finalized identification report; status
advances toward certification.

---

### Stage 5 — Certificate & Handover
**Who:** Receptionist (issue/handover)

1. A **Certificate is issued per stone**, carrying its identification results.
2. Each certificate **downloads as a PDF** for printing and handover. A revoked
   certificate still downloads, watermarked REVOKED.
3. Every certificate carries a **QR code** pointing at a public verification
   page, so anyone holding the paper can confirm it is genuine and has not been
   withdrawn. That page is deliberately anonymous — it describes the stone and
   names nobody. See
   [certificates.md](../engineering/certificates.md).
4. The customer collects the certified stones; handover is recorded.

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
| Note | "Preliminarily identified: Ruby" |

---

## 4b. Where a whole order has got to

A stone has a status. An **order does not** — and that is a deliberate choice
worth understanding before anyone adds the column.

### The stage is derived, never stored

Progress is per stone, and two stones from one visit can genuinely sit at
different stages. But a list of orders still has to answer "where is this one?",
so `OrderStage` gives the honest summary: **the stage the least advanced stone
has reached**. An order is not ready to collect while one of its stones is still
on the bench.

```
identifying → ready_to_bill → awaiting_payment → part_paid
            → in_findings → certified → ready_for_collection → collected
```

plus `empty` for an order whose stones have not been entered yet.

It is computed by `order_stage()` in `apps/orders/selectors.py` from the stone
statuses and the bill, every time it is asked for. Nothing can drift, because
there is nothing to drift *from* — no second copy of the truth to fall out of
step when a stone moves.

The cost is that a derived value cannot be filtered in SQL. So the same rule is
expressed twice: `order_stage()` for one order in Python, and
`orders_at_stage()` as a queryset filter for the Orders screen. A test asserts
the two agree across every stage, which is what keeps the duplication safe.

**If you are tempted to store the stage:** the reason not to is that every stone
transition would then have to remember to recompute it, and the one code path
that forgets produces an order whose badge disagrees with its own stones.

### The hold is stored

One part of an order's state genuinely cannot be derived: `OrderHold`, which is
`active`, `on_hold` or `cancelled`.

"The customer asked us to pause" and "the customer withdrew" are facts about the
*visit*, not about any stone — no combination of stone statuses implies them, so
they are a real column, with a reason, who set it and when. A hold outranks
everything else: a held order reads as `on_hold` whatever its stones are doing.

Holding or releasing an order needs the `orders.hold_order` permission, and a
**paid order cannot be cancelled** — money has changed hands, so the withdrawal
is a refund question rather than a status change.

---

## 5. Key business rules (confirmed)

1. **Reception records only a stone count** (`stone_count`); stones are created
   later, at identification, one record per physical stone.
2. A **report is produced per stone**, and **findings happens after
   payment** (identify → pay → findings → finalize).
3. Reference data (colors, species, treatments, prices, …) is **admin-managed**;
   staff select from fixed lists, not free text.
4. **One Bill per Order** — the customer pays once for the whole batch.
5. Pricing is a **flat fee per stone category** — weight does not change it.
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
