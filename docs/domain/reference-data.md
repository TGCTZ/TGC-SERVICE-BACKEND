# Reference data

The fixed vocabularies the lab picks from instead of typing: lookup tables that
administrators manage, and enums defined in code.

## Lookup tables

Rows in `apps/gems/models.py` (plus two user lookups in `apps/users`), managed on
the frontend under **Administration → Reference data**. Each is a `ReferenceModel`:
a unique `name`, a description and an `is_active` flag - deactivate a row rather
than delete it, so records that already use it keep reading correctly.

| Table | Holds | Note |
| --- | --- | --- |
| `StoneCategory` | Pricing tiers | `price` is the flat fee per stone; null means unpriced, and a bill refuses to include an unpriced stone |
| `StoneType` | Ruby, sapphire… | Belongs to a category, which prices it |
| `Species`, `Variety` | Mineral species and their varieties | A variety name is unique within its species |
| `Color` | Colours | Each in a `ColorGroup` family |
| `Origin` | Countries of origin | |
| `ShapeCut` | Shapes and cuts | |
| `Instrument` | Lab instruments | Listed on the certificate, ticked when used |
| `UserStatus`, `Gender` | For user accounts | New accounts start `Active` |

## Enums

Choices that code depends on live in `apps/gems/enums.py`, below the apps that
use them so several can share one without importing each other: stone status,
weight unit, transparency, nature, treatment, optic character, bill status,
order hold, certificate status, colour group, and region. The frontend mirrors
the ones it displays (for example `features/stones/data/enums.ts`).

## Tanzania's regions

A customer's `region` is one of the country's **31 administrative regions** - 26
on the mainland and 5 in Zanzibar - defined as `Region` in `apps/gems/enums.py`
and mirrored in `frontend/src/lib/regions.ts` for the searchable dropdown.

- **Source.** Checked against the official list in September 2026; the newest
  region is Songwe, split from Mbeya in 2016. When a region is created or
  renamed, update both files and add a migration if values change.
- **Names.** Labels are the official Swahili names - Pwani, not Coast; Kaskazini
  Pemba, not Pemba North. The English names are kept as search aliases in
  `lib/regions.ts`, so typing "coast" in the dropdown finds Pwani.
- **Stored values** are lower-case codes (`dar_es_salaam`); the API accepts
  nothing else, so free text cannot creep back in.
- **Text from before the list.** `normalize_region()` in `apps/gems/regions.py`
  reads hand-typed text - "arusha region", "DSM", "Coast" - as a region where it
  is unambiguous, and returns `None` otherwise ("Zanzibar" could be five). The
  migration that introduced the list used it and **kept** whatever it could not
  read; the customer form shows such a value flagged until someone picks the
  region. Statistics display it as typed.
