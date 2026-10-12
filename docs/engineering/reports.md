# Financial and operational reports

Reports is a read-only app with no report tables or workflow writes. It provides
two permission-filtered pages: Financial reports and Operational reports.

## API

All routes are authenticated and live under `/api/v1/reports/`:

| Route | Purpose |
|---|---|
| `/` | Catalog of authorized report pages and sections. |
| `/financial/` | Financial summaries and a selected detail section. |
| `/operational/` | Operational summaries and a selected detail section. |
| `/financial/export/` | Complete authorized financial report as XLSX or PDF. |
| `/operational/export/` | Complete authorized operational report as XLSX or PDF. |

Query parameters are `from_date` and `to_date` (inclusive ISO dates), `section`,
`customer`, `status`, `provider`, `stone_type`, `page`, and `page_size` (up to 100).
Exports use `file_type=xlsx` or `file_type=pdf`; pagination does not limit exports.
Dates default to this month through today in Africa/Dar_es_Salaam. Reversed or
malformed ranges are rejected. Export limits cover all sections and reject more
than 10,000 rows without truncation.

Financial sections are `billing`, `collections`, `exceptions`, and `outstanding`.
Operational sections are `orders`, `stones`, `findings`, and `certificates`.
The response uses the standard `count`, `next`, `previous`, `results` envelope,
plus `sections` (whole-result totals), column metadata, authorized filter choices,
the effective range, and a generation timestamp. Monetary values are decimal
strings and totals are grouped by currency.

## Dates and permissions

- Billing and outstanding use bill issue dates. Outstanding balances are current,
  using processed payments applied to the bill, including payments after the range.
  Blank payment currencies inherit the bill currency; a different currency is not
  subtracted without a conversion rule.
  Cancelled bills and non-positive balances are excluded from outstanding.
- Collections use transaction dates and processed payments. Exceptions remain
  separate and never contribute to confirmed collection totals.
- Orders use received dates; stones use registration dates; findings use finalization
  dates; certificates use issue dates, including later-revoked certificates.
- Missing event dates are counted separately across all dates after other filters.
  They are not silently replaced by creation dates or included in dated totals.
- Bill status filters apply to billing/outstanding; payment provider filters apply
  to collections/exceptions. Customer filters apply across a page; stone type is
  operational only. Orders with matching stones are counted once.
- Each section requires its source model's view permission. Outstanding needs
  both bill and payment view permissions. Unauthorized sections and their totals
  are omitted; direct requests for them are refused. Filter choices come only
  from authorized source data, rather than requiring customer-catalog access.
- A page also requires `core.module_reports` and its own gate:
  `core.report_financial` or `core.report_operational`. The Roles dialog groups
  these three permissions under Reports. The migration grants existing report
  readers the corresponding gates without resetting customized roles.
- Export permissions are identical to screen permissions. XLSX cells containing
  user text remain strings, preventing formula interpretation.

The frontend uses the existing API client, TanStack Query/Router, `DataTable`,
pagination helpers, app-wide formatting, and layout components. Filters and the
active detail page are URL-owned. `/` and `/reports` redirect to Financial reports
when accessible, otherwise Operational reports, or the existing forbidden page.
Legacy Management custom dates and named ranges are preserved during redirection.
