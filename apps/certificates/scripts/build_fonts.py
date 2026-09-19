"""Build the subset woff2 faces the certificate PDF embeds.

Run once, by hand, and commit the result. Fonts are *vendored*, never fetched at
render time - a document that reaches for the network to render is a document
that fails to render when the network does.

Why subset at all: the certificate embeds each face as a ``data:`` URI, the same
way it embeds the lab's marks, so the bytes are read and base64-encoded in the
rendering process. The upstream variable fonts are ~2MB together. Instancing
them to the two weights the document uses and cutting the character set to Latin
takes that to well under a tenth, for glyphs no certificate will ever ask for.

Both faces carry an optical-size axis. Pinning it matters here: ``opsz`` is the
type designer's own instruction for how the face should be drawn at a given
size, and this document sets nothing above 13pt. Left at its default the text
would be drawn with the proportions of a headline.

Both are SIL Open Font License 1.1. See ``static/certificates/fonts/README.md``.

Usage::

    python apps/certificates/scripts/build_fonts.py
"""

import io
import sys
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "certificates" / "fonts"

SOURCES = {
    "source-serif-4": "https://github.com/google/fonts/raw/main/ofl/sourceserif4/SourceSerif4%5Bopsz%2Cwght%5D.ttf",
    "inter": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
}

#: Optical size to pin, per family, in points.
#:
#: The certificate's largest type is the 13pt lab name and its smallest is the
#: 6.5pt statement, so 11 sits in the middle of what the serif actually sets.
#: Inter's axis bottoms out at 14, which is already its text-optimised end.
OPTICAL_SIZE = {"source-serif-4": 11, "inter": 14}

#: Weights to instance. Regular for reading, SemiBold for labels and titles;
#: 600 rather than 700 because a 7.5pt uppercase label in true bold turns into
#: a black smear at print resolution.
WEIGHTS = {"regular": 400, "semibold": 600}

#: What the document can actually print.
#:
#: Latin-1 covers English and the punctuation the layout uses. Latin Extended-A
#: is there for names: a certificate carries the gemmologists' names as typed,
#: and a subset that silently drops a diacritic misspells a person on a legal
#: document. The named marks are the tick in the instruments column, the middle
#: dot in the footer, and the em dash every unrecorded finding prints.
UNICODES = [
    "U+0020-007E",  # Basic Latin
    "U+00A0-00FF",  # Latin-1 Supplement
    "U+0100-017F",  # Latin Extended-A
    "U+2013-2014",  # en dash, em dash
    "U+2018-201D",  # curly quotes
    "U+00B7",  # middle dot - footer separator
    "U+2713",  # check mark - instruments column
]


def _fetch(url: str) -> bytes:
    """Download one upstream variable font."""
    # Checked rather than assumed: urlopen will happily honour a file: URL, and
    # the whole point of vendoring fonts is knowing where they came from.
    if not url.startswith("https://"):
        raise ValueError(f"Refusing to fetch a font over a non-https URL: {url}")

    print(f"  fetching {url.rsplit('/', 1)[-1]}")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
        return response.read()


def _build(family: str, raw: bytes, style: str, weight: int) -> Path:
    """Instance one weight, subset it to Latin, and write it as woff2."""
    font = TTFont(io.BytesIO(raw))

    # Pin both axes, collapsing the variable font to a single static instance.
    font = instancer.instantiateVariableFont(
        font, {"wght": weight, "opsz": OPTICAL_SIZE[family]}, inplace=True
    )

    options = subset.Options()
    options.layout_features = ["kern", "liga", "tnum", "calt"]
    options.desubroutinize = True
    # Keep the licence and family records: a stripped font with no OFL notice in
    # its name table is a licence problem, not just an incomplete one.
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
    options.notdef_outline = True

    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=subset.parse_unicodes(",".join(UNICODES)))
    subsetter.subset(font)

    font.flavor = "woff2"
    path = OUT_DIR / f"{family}-{style}.woff2"
    font.save(path)
    return path


def main() -> int:
    """Fetch, instance and subset every face, writing woff2 into the app."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for family, url in SOURCES.items():
        raw = _fetch(url)
        for style, weight in WEIGHTS.items():
            path = _build(family, raw, style, weight)
            print(f"  {path.name:34} {path.stat().st_size / 1024:6.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
