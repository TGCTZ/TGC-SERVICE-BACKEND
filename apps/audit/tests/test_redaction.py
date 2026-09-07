"""System-log reading and secret redaction."""

from apps.audit.services import REDACTION, read_log, redact


def test_redacts_password_assignments():
    """A password value never survives into the API response."""
    assert "hunter2" not in redact("login attempt password: hunter2 for user 4")
    assert REDACTION in redact("login attempt password: hunter2 for user 4")


def test_redacts_json_style_secrets():
    """JSON-ish payloads are redacted too."""
    line = '{"email": "a@b.com", "password": "s3cret", "token": "abc.def"}'
    result = redact(line)

    assert "s3cret" not in result
    assert "abc.def" not in result
    assert "a@b.com" in result  # non-secret fields are left readable


def test_redacts_bearer_tokens():
    """Authorization headers are stripped of their token."""
    result = redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")

    assert "eyJhbGciOiJIUzI1NiJ9" not in result


def test_read_log_parses_and_orders_newest_first(tmp_path):
    """Entries come back parsed, redacted and in reverse chronological order."""
    log = tmp_path / "app.log"
    log.write_text(
        "[2026-01-01 10:00:00] INFO django: first message\n"
        "[2026-01-01 11:00:00] ERROR django: second message password: leaked\n",
        encoding="utf-8",
    )

    entries = read_log(log)

    assert len(entries) == 2
    assert entries[0]["level"] == "ERROR"
    assert "leaked" not in entries[0]["message"]


def test_read_log_filters_by_level(tmp_path):
    """The level filter narrows the result set."""
    log = tmp_path / "app.log"
    log.write_text(
        "[2026-01-01 10:00:00] INFO django: fine\n"
        "[2026-01-01 11:00:00] ERROR django: broken\n",
        encoding="utf-8",
    )

    entries = read_log(log, level="ERROR")

    assert len(entries) == 1
    assert entries[0]["message"] == "broken"


def test_read_log_handles_a_missing_file(tmp_path):
    """A log file that does not exist yet is not an error."""
    assert read_log(tmp_path / "nope.log") == []
