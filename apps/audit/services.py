"""Reading and redacting the application log file."""

import re
from pathlib import Path

# Matches the "standard" formatter configured in settings.LOGGING.
LINE = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+(?P<level>\w+)\s+(?P<logger>[^:]+):\s+(?P<message>.*)$"
)

# Secrets that must never leave the server, even to an administrator. Matched
# case-insensitively against "key: value", "key=value" and JSON-ish forms.
SENSITIVE_KEYS = (
    "password",
    "password_confirm",
    "current_password",
    "token",
    "refresh",
    "access",
    "secret",
    "api_key",
)

REDACTION = "[REDACTED]"

_PATTERNS = [
    re.compile(
        rf"(?P<prefix>[\"\']?{key}[\"\']?\s*[:=]\s*)(?P<value>[\"\']?[^\s,;}}\"\']+)",
        re.IGNORECASE,
    )
    for key in SENSITIVE_KEYS
]
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
# Authorization is handled separately: its value is "Bearer <token>", so the
# generic key/value pattern would stop at the word "Bearer" and leave the token.
_AUTH_HEADER = re.compile(
    r"(?P<prefix>[\"']?authorization[\"']?\s*[:=]\s*)[^,;}\n\"']+", re.IGNORECASE
)

# Reading an unbounded log file would exhaust memory on a busy server, so only
# the newest slice is ever touched.
MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 5000


def redact(text: str) -> str:
    """Replace secret values in a log line with a placeholder."""
    # Order matters: the whole Authorization value goes first, then any bare
    # inline Bearer token, then the simple key/value secrets.
    text = _AUTH_HEADER.sub(rf"\g<prefix>{REDACTION}", text)
    text = _BEARER.sub(rf"\g<1>{REDACTION}", text)
    for pattern in _PATTERNS:
        text = pattern.sub(rf"\g<prefix>{REDACTION}", text)
    return text


def read_log(
    path: Path, *, level: str | None = None, search: str | None = None
) -> list[dict]:
    """Parse the tail of the log file into redacted entries, newest first.

    Args:
        path: Location of the log file.
        level: Optional level name to filter by, e.g. ``"ERROR"``.
        search: Optional case-insensitive substring to match in the message.

    Returns:
        A list of dicts with timestamp, level, logger and message keys.
    """
    if not path.exists():
        return []

    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - MAX_BYTES))
        raw = handle.read().decode("utf-8", errors="replace")

    entries = []
    # The first line is dropped when the file was truncated mid-line by the seek.
    lines = raw.splitlines()[1:] if size > MAX_BYTES else raw.splitlines()

    for line in reversed(lines):
        match = LINE.match(line)
        if not match:
            continue
        entry = match.groupdict()
        if level and entry["level"].upper() != level.upper():
            continue
        entry["message"] = redact(entry["message"])
        if search and search.lower() not in entry["message"].lower():
            continue
        entries.append(entry)
        if len(entries) >= MAX_ENTRIES:
            break
    return entries
