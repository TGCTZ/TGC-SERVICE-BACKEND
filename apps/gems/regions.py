"""Reading a free-text region as one of Tanzania's regions.

Before regions were a fixed list, reception typed them by hand, so the stored
values run from "Arusha" to "arusha region", "DSM" and "Pemba North". This turns
such text into a :class:`~apps.gems.enums.Region` value where it can say which
region was meant, and into None where it cannot - it never guesses. Plain
"Zanzibar", for instance, could be any of five regions.
"""

import re

from apps.gems.enums import Region

#: Other ways of writing a region: the English names, and the shorthand seen
#: at reception. Written lower-case and unpunctuated, as :func:`_key` leaves
#: text; each region's own value and label are matched without being listed.
ALIASES = {
    Region.DAR_ES_SALAAM: ("dsm", "dar", "daressalaam"),
    Region.PWANI: ("coast",),
    Region.KAGERA: ("west lake",),
    Region.KASKAZINI_PEMBA: ("pemba north", "north pemba"),
    Region.KUSINI_PEMBA: ("pemba south", "south pemba"),
    Region.KASKAZINI_UNGUJA: (
        "unguja north",
        "north unguja",
        "zanzibar north",
        "north zanzibar",
    ),
    Region.KUSINI_UNGUJA: (
        "unguja south",
        "south unguja",
        "zanzibar south",
        "south zanzibar",
    ),
    Region.MJINI_MAGHARIBI: (
        "urban west",
        "zanzibar urban west",
        "zanzibar urban",
        "zanzibar west",
        "zanzibar town",
        "zanzibar city",
    ),
}


def _key(text: str) -> str:
    """Lower-case words only, with "region" / "mkoa wa" dropped."""
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    if words[:2] == ["mkoa", "wa"]:
        words = words[2:]
    if words[-1:] == ["region"]:
        words = words[:-1]
    return " ".join(words)


def _lookup() -> dict[str, str]:
    table = {}
    for region in Region:
        table[_key(region.value)] = region.value
        table[_key(region.label)] = region.value
    for region, aliases in ALIASES.items():
        for alias in aliases:
            table[_key(alias)] = region.value
    return table


_LOOKUP = _lookup()


def normalize_region(text: str | None) -> str | None:
    """The region value ``text`` names, or None when it names none clearly.

    Args:
        text: A region as someone typed it, e.g. "arusha region" or "DSM".
    """
    if not text:
        return None
    return _LOOKUP.get(_key(text))
