# Operations

How the API is configured and what to run when it is deployed. Local setup is in
the [README](../../README.md#quick-start).

## Settings modules

| Entry point | Settings module |
| --- | --- |
| `manage.py` | `config.settings.development` |
| `config/wsgi.py`, `config/asgi.py` | `config.settings.production` |
| `pytest` | `config.settings.test` |

Production forces `DEBUG = False`, redirects to HTTPS, sends HSTS, marks cookies
secure and serves JSON only (no browsable API). It expects to sit behind a proxy
that sets `X-Forwarded-Proto`.

## Configuration

Every value is read from the environment (or `.env`) in
`config/settings/base.py`. `.env.example` lists them all; a test fails if a
setting reads a variable that file does not mention.

| Variable | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | - | **Required.** No fallback, so a missing key stops the app. |
| `DEBUG` | `False` | Never true in production. |
| `ALLOWED_HOSTS` | - | Comma-separated. Required once `DEBUG` is off. |
| `DATABASE_URL` | - | **Required.** `postgres://user:password@host:5432/name`. |
| `CORS_ALLOWED_ORIGINS` | - | The frontend's origin(s), comma-separated. |
| `TIME_ZONE` | `UTC` | Storage and API timestamps. Leave at UTC. |
| `LAB_TIME_ZONE` | `Africa/Dar_es_Salaam` | The lab's calendar: which day a statistic counts an event on. |
| `LOG_LEVEL` | `INFO` | For `logs/app.log`, which the System Logs screen reads. |
| `JWT_ACCESS_MINUTES` | `60` | How long a revoked session can keep working - a security setting. |
| `JWT_REFRESH_DAYS` | `14` | How long a user stays signed in without re-entering a password. |
| `FRONTEND_URL` | `http://localhost:5173` | The sign-in link in the new-account email. |
| `EMAIL_URL` | `consolemail://` | Outgoing mail, e.g. `smtp+tls://user:password@host:587`. The default prints mail to the log instead of sending it. |
| `DEFAULT_FROM_EMAIL` | `Tanzania Gemmological Centre <no-reply@tgc.go.tz>` | Sender of the new-account email. |
| `CERTIFICATE_LAB_NAME` | `Tanzania Gemmological Centre` | Used in emails, the verify page, and the certificate's text header if the banner image is missing. |
| `CERTIFICATE_LAB_ADDRESS` | empty | Printed on the certificate. |
| `CERTIFICATE_MINISTRY_NAME` | `Ministry of Minerals` | The certificate's text header, if the banner image is missing. |
| `CERTIFICATE_VERIFY_BASE_URL` | `http://localhost:8000` | Absolute base of the QR link on every certificate. Must be publicly reachable. |
| `GEPG_SIMULATE` | `False` | Fake control numbers and payments, to walk the pipeline offline. Needs `DEBUG` too. |
| `GEPG_*_URL`, `GEPG_*_CODE` | empty | Gateway endpoints and the lab's codes - see [GePG integration](../gepg/README.md). |
| `GEPG_USE_DIGITAL_SIGNATURE` | `False` | Sign payloads with the PKCS#12 key below. |
| `GEPG_CERTIFICATE_PASSWORD` | empty | The key's passphrase. |
| `GEPG_PRIVATE_KEY_PATH`, `GEPG_PUBLIC_CERT_PATH` | `certificates/private.pfx`, `certificates/public.pfx` | The signing key and the gateway's certificate. |
| `GEPG_BILL_EXPIRY_DAYS` | `365` | How long a control number stays payable. |

## Before the first deploy

WeasyPrint needs system libraries at import time, not just when a PDF is drawn -
without them the whole app fails to start. See the
[README](../../README.md#quick-start) for the package list.

Set up email before anyone creates an account: without `EMAIL_URL`, the
credentials email only reaches the server log (the creator still sees the
temporary password on screen).

## Deploying

Every deploy:

```bash
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput   # the Django admin's assets
```

The first deploy only, after `migrate`:

```bash
uv run python manage.py setup_roles       # create the six roles
uv run python manage.py createsuperuser   # the first account; it can create the rest
```

A Django superuser ranks at the top of the role hierarchy, so it can create
admins and managers from the Users screen. Do not run `seed` in production - it
creates demo accounts with a known password.

### `setup_roles` resets roles

`setup_roles` sets each declared role's permissions to exactly what
`apps/users/roles.py` says, including `admin`. Anything changed on the roles
screen since is overwritten. Run it only when `roles.py` has changed - a new role
or a new permission - and check first whether anyone has edited roles by hand.
Roles created on the screen are left alone (and reported as stale); `--prune`
deletes them.

## Health checks

| Endpoint | Returns |
| --- | --- |
| `GET /api/health/` | 200 while the process runs; touches nothing else. Use for liveness. |
| `GET /api/health/ready/` | 503 if the database is unreachable or migrations are pending. Use for readiness. |

## What to back up

- The database.
- `media/` - uploaded stone photographs and avatars. Certificates print from the
  photo stored when they were issued, so losing these breaks old certificates.
- `certificates/` - the GePG signing key, if signing is on.
