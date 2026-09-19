# Certificate assets

Images embedded in the certificate PDF, read by `services/assets.py` and
inlined as `data:` URIs — so this directory does **not** need `collectstatic`
to have run, and WeasyPrint needs no `base_url`.

| File | Used for | Status |
|---|---|---|
| `tgc-logo.png` | Header, right | Present — converted from the frontend's `tgc-logo.webp` |
| `coat-of-arms.png` | Header, left | Present — the legacy system's `armcoat.png`. Tighter crop than the frontend's `coat-of-arm.webp`, so it reads larger in the same 22mm box |
| `official-stamp.png` | Stamp box, column 1 | Present — the lab's ink stamp |

A missing file is not an error: `asset_data_uri` logs a warning once and the
template leaves the box empty under its caption — for the stamp that is the
space the lab stamps by hand, so no placeholder text is printed. Drop the
file in with the exact name above and it appears on the next render, no code
change.

## Neither mark is its source file byte-for-byte

Both the emblem and the stamp arrived from the legacy system with the image
editor's **transparency checkerboard rendered into the pixels** and no alpha
channel — #EEEEEE cells behind the emblem, #CBCBCB behind the stamp. They look
transparent in a thumbnail and print as a grey grid behind the mark.

`scripts/clean_backdrop.py` removes it and is how each file here was produced,
so the difference from the legacy original is deliberate, not corruption:

```bash
python apps/certificates/scripts/clean_backdrop.py <source.png> coat-of-arms.png
python apps/certificates/scripts/clean_backdrop.py <source.png> official-stamp.png
```

If you replace either mark, check the result on a rendered certificate rather
than in a file browser — a browser shows its *own* checkerboard for real
transparency, so a baked-in one is invisible exactly where you would look for
it.

Prefer PNG with transparency. The header marks render at up to 22mm tall and
the stamp at up to 50mm, so roughly 600px on the long edge is ample; anything
larger just inflates every PDF, since the bytes are embedded per document.
