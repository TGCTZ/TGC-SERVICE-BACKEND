# Certificate assets

Images embedded in the certificate PDF, read by `services/assets.py` and
inlined as `data:` URIs — so this directory does **not** need `collectstatic`
to have run, and WeasyPrint needs no `base_url`.

| File | Used for | Status |
|---|---|---|
| `tgc-logo.png` | Header, right | Present — converted from the frontend's `tgc-logo.webp` |
| `coat-of-arms.png` | Header, left | **Missing** — supply the national coat of arms |
| `official-stamp.png` | Stamp box, column 1 | **Missing** — supply the lab's official stamp |

A missing file is not an error: `asset_data_uri` logs a warning once and the
template renders a labelled empty box in its place. Drop the file in with the
exact name above and it appears on the next render, no code change.

Prefer PNG with transparency. The header marks render at up to 20mm tall and
the stamp at up to 22mm, so roughly 600px on the long edge is ample; anything
larger just inflates every PDF, since the bytes are embedded per document.
