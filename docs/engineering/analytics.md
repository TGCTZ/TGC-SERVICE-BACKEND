# Management statistics

The figures behind the dashboard's Management tab: volume, money, speed and the
market mix, over a period the reader picks. Read-only aggregates over the other
apps; the `analytics` app owns no data.

Code: `apps/analytics/selectors.py` (what is counted), `apps/analytics/periods.py`
(the period rules), `apps/analytics/views.py` (the endpoints).

## Endpoints

All `GET`, all under `/api/v1/analytics/`, all behind `analytics.view_statistics`
(held by manager, admin and superadmin; grantable per role on the roles screen).

| Endpoint | Answers |
| --- | --- |
| `summary/` | The KPI row: stones received, certificates issued, revenue collected - each with the previous equal-length period - and money outstanding now |
| `volume/` | Orders, stones received and certificates issued per bucket; new vs returning customers; hold and cancel rates; revoked certificates |
| `revenue/` | Per currency: billed vs collected per bucket, collection rate, average fee per stone, outstanding money aged by bill age, expired bills; time to pay; payment channels |
| `turnaround/` | Days from order to certificate (median, mean, 90th percentile); days waited in each stage; work in the lab now, by days waiting; findings and certificates per person |
| `market/` | Species, varieties, origins, nature, treatments (from finalized reports), stone types, customer regions |

**The exact definition of every figure is the docstring of its selector** - kept
next to the query, so the two cannot drift. When management asks what a number
means, answer from there.

## Periods

Query parameters `from` and `to` (ISO dates, both inclusive). Without them: the
twelve calendar months to today. A range must run forwards and cover at most
3 × 366 days (400 otherwise).

- **Days are the lab's days.** Storage is UTC; each event is counted on its date
  in `LAB_TIME_ZONE` (Africa/Dar_es_Salaam). A payment at 22:00 in Dar es Salaam
  belongs to that day there, not the next UTC day.
- **Bucket size follows the range**: days up to 31 days, ISO weeks (from Monday)
  up to 26 weeks, months beyond. The response says which, in `range.granularity`.
- **Series are zero-filled**, so a quiet bucket is a zero rather than a gap.
- **Comparisons** use the equally long period ending the day before `from`.

## Rules every figure keeps

- **Money is never added across currencies.** Every amount is per currency, even
  though the lab bills in TZS today.
- **"Received" means handed in at reception** - `Order.received_date` and
  `Order.stone_count`. A `Stone` row exists only once the bench has identified it.
- **Soft-deleted rows are excluded** (default managers throughout).
- **Grouped queries call `.order_by()` first.** Most models have a default
  ordering, and Django adds ordering columns to `GROUP BY`, which splits every
  aggregate silently.
- **Turnaround starts at the order**, when the lab took the stones in, and stages
  are read off consecutive `StatusHistory` rows.

## Thresholds

Tuned to a job that normally takes one to three days when payment is prompt:

| Constant | Bands | Used for |
| --- | --- | --- |
| `AGE_BUCKETS` | under 1 day · 1 day · 2-3 days (*watch*) · 4-7 days (*late*) · over 7 days (*late*) | Work in the lab now |
| `RECEIVABLE_AGES` | 0-7 · 8-30 · 31-90 · over 90 days since issue | Outstanding money |

The frontend badges *watch* and *late* from the status the API sends; change a
threshold in the tuple and the screen follows.

## Adding a figure

1. Compute it in the section's selector, and define it in that selector's
   docstring: what is counted, by which date, and what is left out.
2. Test it in `apps/analytics/tests/test_statistics.py` with hand-built rows -
   including an edge that would catch a wrong date field or a currency mix.
3. Add the field to the section's type in
   `frontend/src/features/dashboard/data/analytics.ts` and render it.

## Demo data

`manage.py seed --orders 150 --history-months 12` on an empty database spreads
orders over a year and carries each as far through the pipeline as its age allows,
so every chart has something to show.
