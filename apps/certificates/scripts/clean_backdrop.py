"""Strip a baked-in transparency checkerboard from a certificate asset.

Run by hand and commit the result - the same arrangement as ``build_fonts.py``.
This exists so an asset's provenance is a script rather than a story: the files
in ``static/certificates/img`` are not the legacy system's files byte-for-byte,
and a maintainer diffing the two deserves to know why.

Some of the legacy artwork was exported from an image editor with the editor's
*transparency checkerboard* rendered into the pixels, and no alpha channel at
all. It looks transparent in a thumbnail and prints as a grey grid behind the
mark. Both the coat of arms and the official stamp arrived this way, in
different greys - #EEEEEE and #C8C8C8 - which is why the grey is detected
rather than hard-coded.

Two simpler approaches are wrong, so note what this does instead:

* A global colour swap punches holes through the artwork's own white - the
  emblem's tusks, its banner, the wave section of the shield.
* A flood fill from the border leaves whatever the artwork *encloses*: the gaps
  between each figure's arm and the shield, the inside of the stamp's frame.

So the seeds are the checkerboard's own grey cells, wherever they fall, and the
fill spreads from them through neutral light pixels. Artwork whites hold none
of the checker grey, so they are never seeded, and the dark outlines stop the
fill from reaching them. Anything with colour in it - ink, skin, sky - fails
the neutrality test and is never touched.

Usage - the output name is the filename ``services/assets.py`` looks for::

    python apps/certificates/scripts/clean_backdrop.py ~/armcoat.png coat-of-arms.png
    python apps/certificates/scripts/clean_backdrop.py ~/stamp.png official-stamp.png
"""

import sys
from collections import Counter, deque
from pathlib import Path

from PIL import Image

# Resolved by path rather than imported from ``services.assets``: importing the
# app package pulls in Django's model graph, and a standalone script should not
# need a configured settings module to crop a PNG.
OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "certificates" / "img"

#: How far the three channels may diverge and still count as neutral. Keeps the
#: fill off ink, skin, sky and every other tinted pixel in the artwork.
NEUTRAL_TOLERANCE = 6

#: The darkest grey a checkerboard cell is assumed to use. Below this we are
#: looking at artwork, not backdrop.
DARKEST_CHECKER = 150

#: How far either side of the detected grey still counts as the same cell,
#: allowing for the odd resampled pixel at a cell boundary.
CELL_SPREAD = 10


def _neutral(pixel: tuple[int, ...]) -> int | None:
    """The pixel's grey level, or None if it carries colour."""
    r, g, b = pixel[:3]
    if max(r, g, b) - min(r, g, b) >= NEUTRAL_TOLERANCE:
        return None
    return r


def _detect_checker_grey(image: Image.Image) -> int:
    """The grey the checkerboard's darker cell uses.

    Detected as the commonest neutral tone that is neither white nor dark
    enough to be artwork. Hard-coding it worked for one asset and broke on the
    next, which is the whole reason this is a function.
    """
    counts: Counter[int] = Counter()
    # getcolors over a pixel loop: it is exact for the palette sizes these
    # assets use, and far quicker than walking every pixel in Python.
    for count, pixel in image.convert("RGB").getcolors(maxcolors=1 << 24) or []:
        value = _neutral(pixel)
        if value is not None and DARKEST_CHECKER <= value < 250:
            counts[value] += count
    if not counts:
        raise SystemExit("No checkerboard grey found; the asset looks clean.")
    return counts.most_common(1)[0][0]


def clean(source: Path, name: str) -> Path:
    """Write ``source`` into the asset directory, backdrop made transparent."""
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    pixels = image.load()

    grey = _detect_checker_grey(image)
    floor = grey - CELL_SPREAD
    print(f"  checkerboard grey detected at #{grey:02X}{grey:02X}{grey:02X}")

    def is_seed(x: int, y: int) -> bool:
        value = _neutral(pixels[x, y])
        return value is not None and abs(value - grey) <= CELL_SPREAD

    def is_backdrop(x: int, y: int) -> bool:
        value = _neutral(pixels[x, y])
        return value is not None and value >= floor

    seen = [[False] * width for _ in range(height)]
    queue = deque((x, y) for y in range(height) for x in range(width) if is_seed(x, y))

    cleared = 0
    while queue:
        x, y = queue.popleft()
        if not (0 <= x < width and 0 <= y < height) or seen[y][x]:
            continue
        seen[y][x] = True
        if not is_backdrop(x, y):
            continue
        pixels[x, y] = (255, 255, 255, 0)
        cleared += 1
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    destination = OUT_DIR / name
    image.save(destination, optimize=True)
    share = 100 * cleared / (width * height)
    print(f"  cleared {cleared} backdrop px ({share:.1f}%) -> {destination.name}")
    return destination


def main() -> int:
    """Clean the source named on the command line into the asset directory."""
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    clean(Path(sys.argv[1]), sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
