"""The documentation stays in step with the code it describes.

Two cheap checks that CI runs with the rest of the suite: prose accuracy still
needs a reviewer, but these two kinds of drift do not.
"""

import importlib.util
import re
from pathlib import Path

from django.conf import settings

BACKEND = Path(settings.BASE_DIR)
ENV_READ = re.compile(r'env(?:\.\w+)?\(\s*"([A-Z][A-Z0-9_]*)"')


def test_every_setting_read_from_the_environment_is_in_env_example():
    """Every variable the settings read is listed in ``.env.example``.

    One it never mentions is one nobody configuring a new server will know to set.
    """
    read = set()
    for module in (BACKEND / "config" / "settings").glob("*.py"):
        read |= set(ENV_READ.findall(module.read_text(encoding="utf-8")))
    documented = (BACKEND / ".env.example").read_text(encoding="utf-8")

    missing = sorted(name for name in read if name not in documented)

    assert not missing, f"Add to .env.example: {', '.join(missing)}"


def test_documentation_links_resolve(capsys):
    """Every relative link in the docs lands somewhere.

    ``scripts/check_docs.py`` also runs as a pre-commit hook, which can be skipped.
    """
    path = BACKEND / "scripts" / "check_docs.py"
    spec = importlib.util.spec_from_file_location("check_docs", path)
    check_docs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_docs)

    assert check_docs.main() == 0, capsys.readouterr().out
