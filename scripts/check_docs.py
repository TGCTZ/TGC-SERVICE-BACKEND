#!/usr/bin/env python
"""Fail when the documentation links to something that does not exist.

Docs rot quietly: an app is renamed and the sentence describing it stays behind,
still looking authoritative. This walks every markdown file, resolves each
relative link, and reports the ones that no longer land anywhere.

It checks *links*, never prose. Whether a description is still accurate needs a
human; whether ``apps/catalog/urls.py`` still exists does not - and that is the
failure that actually happened here.

Run: uv run python scripts/check_docs.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "node_modules", ".git", "__pycache__", "htmlcov"}
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
EXTERNAL = ("http://", "https://", "mailto:", "#")


def markdown_files() -> list[Path]:
    """Every markdown file in the project, excluding vendored trees."""
    return [
        path
        for path in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.parts)
    ]


def main() -> int:
    """Report broken relative links; exit non-zero if there are any."""
    broken: list[str] = []
    checked = 0

    for path in markdown_files():
        for _label, target in LINK.findall(path.read_text(encoding="utf-8")):
            if target.startswith(EXTERNAL):
                continue
            # Strip any anchor: the file is what we can verify.
            target = target.split("#", 1)[0]
            if not target:
                continue
            checked += 1
            if not (path.parent / target).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")

    if broken:
        print(f"{len(broken)} broken reference(s) in the docs:\n")
        for entry in broken:
            print(f"  {entry}")
        print("\nEither the path changed, or the doc describes something gone.")
        return 1

    print(f"docs check - {checked} relative links, all resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
