# Certificate assets

Images embedded in the certificate PDF, read by `services/assets.py` and
inlined as `data:` URIs — so this directory does **not** need `collectstatic`
to have run, and WeasyPrint needs no `base_url`.

| File | Used for | Status |
|---|---|---|
| `tgc-logo.png` | Header, right | Present — converted from the frontend's `tgc-logo.webp` |
| `coat-of-arms.png` | Header, left | Present — converted from the frontend's `src/assets/coat-of-arm.webp`, quantised to a 256-colour palette (~90KB rather than ~370KB, and these bytes ride in every PDF) |
| `official-stamp.png` | Stamp box, column 1 | **Missing** — supply the lab's official stamp |

A missing file is not an error: `asset_data_uri` logs a warning once and the
template leaves the box empty under its caption — for the stamp that is the
space the lab stamps by hand, so no placeholder text is printed. Drop the
file in with the exact name above and it appears on the next render, no code
change.

Prefer PNG with transparency. The header marks render at up to 22mm tall and
the stamp at up to 50mm, so roughly 600px on the long edge is ample; anything
larger just inflates every PDF, since the bytes are embedded per document.
