# Certificate fonts

The two typefaces the certificate PDF embeds, read by `services/assets.py`
(`font_faces()`) and inlined as `data:` URIs — so this directory does **not**
need `collectstatic` to have run, and WeasyPrint needs no `base_url`.

| File | Family in CSS | Weight | Used for |
|---|---|---|---|
| `source-serif-4-regular.woff2` | `TGC Serif` | 400 | reserve |
| `source-serif-4-semibold.woff2` | `TGC Serif` | 600 | lab name, title, column headers, labels |
| `inter-regular.woff2` | `TGC Sans` | 400 | values, readings, comments, statement |
| `inter-semibold.woff2` | `TGC Sans` | 600 | reserve |

## Why these are embedded rather than named

The render host carries DejaVu and Ubuntu only, and the system package list in
`backend/README.md` installs no font package at all. A face that is *named* but
not embedded does not fail — it **substitutes**, silently, and the lab issues a
subtly different document with nobody the wiser. That is exactly how this
template came to be set in DejaVu Serif. Embedding removes the host from the
question entirely.

A missing file here is not an error: `font_faces()` skips it and the template's
fallback stack takes over, so the certificate still renders — just not in its
own clothes. Watch the logs for `Certificate asset 'font:…' not found`.

## How they were built

Not downloaded as-is. `scripts/build_fonts.py` fetches the upstream variable
fonts and, using fontTools (already a WeasyPrint dependency):

1. **Instances** the variable axes to fixed values — `wght` 400 / 600, and
   `opsz` pinned to the size this document actually sets (11pt for the serif,
   14pt for Inter). The optical-size axis is the designer's own instruction for
   how a face should be drawn at a given size; left at its default, 8pt body
   text is drawn with the proportions of a headline.
2. **Subsets** to Latin-1, Latin Extended-A and the marks the layout uses (`✓`,
   `·`, `—`). Latin Extended-A is not optional: a certificate carries the
   gemmologists' names as typed, and dropping a diacritic misspells a person on
   a legal document.

Result: ~19KB per face instead of ~300KB, and ~74KB total instead of ~2MB. PDF
size is unaffected either way — WeasyPrint subsets again on write — so the win
is repository weight and per-process memory.

To rebuild (needs network):

```bash
python apps/certificates/scripts/build_fonts.py
```

## Licence

Both families are under the **SIL Open Font License 1.1** — see `OFL.txt`.

- Source Serif 4 — Copyright 2014–2023 Adobe (https://adobe.com/type)
- Inter — Copyright 2016–2024 The Inter Project Authors

The subsetting keeps name IDs 13 and 14 (licence description and URL) in each
font, so the embedded copies carry their own licence notice.
