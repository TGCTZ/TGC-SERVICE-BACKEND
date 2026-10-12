# GePG production setup

Use this runbook to configure the new backend on a VPS while keeping the old GePG registration. The old project is a read-only source for its production URLs, service codes, Beem credentials, and signing identity. Do not edit the old project or change the GePG registration.

## Before starting

You need access to the VPS or its secret manager, the new backend deployment, and the old system's production `.env` and private PFX. Do not paste credentials into source files, tickets, chat, or shell commands. The new backend's `.env` and `certificates/` directory are git-ignored; a code deployment will not carry either file to the VPS.

There are three different kinds of values:

| Value | Source | Action |
| --- | --- | --- |
| GePG URLs and service codes | Old production `.env` / existing registration | Copy exactly. Do not generate or edit them. |
| GePG signing key and certificate | Old private PFX | Copy the same identity and re-encrypt the new copy with a new local password. Do not create a replacement key pair unless GePG registers it. |
| Django secret, PFX copy password, Beem credentials | Django / local secret manager / existing Beem account | Generate a new Django secret and PFX password; copy the Beem API credentials from the old production configuration. |

`GEPG_BILL_UPDATE_URL` is not used by this backend and should not be configured. `GEPG_PUBLIC_CERT_PATH` is currently not used to verify inbound callback signatures.

## 1. Collect the existing GePG values

On a secure admin workstation, read the old `.env` without editing it. Record these variable names and their **production** values in the VPS secret manager:

```text
GEPG_BILL_CREATE_URL
GEPG_BILL_CANCEL_URL
GEPG_RECONCILIATION_URL
GEPG_SP_GRP_CODE
GEPG_SYS_CODE
GEPG_SP_CODE
GEPG_SUB_SP_CODE
GEPG_COLL_CENT_CODE
GEPG_GFS_CODE
BEEM_AFRICA_API_KEY
BEEM_AFRICA_SECRET_KEY
```

Copy URLs and codes exactly as configured on the old production system, including scheme, host, port, and path. These values identify the existing GePG integration; inventing new codes or replacing an old URL with a guessed address will break the registration. Do not copy test/sandbox values when preparing production.

## 2. Re-encrypt a copy of the signing PFX

The private PFX contains the signing identity GePG already recognizes. Keep the original old-system file unchanged. Transfer a copy to a restricted workstation or secure VPS staging directory, then save the following script as `rewrap_gepg_pfx.py`. It loads and writes the PFX in memory, prompts for passwords without echoing them, and verifies the new file.

Generate a **new** PFX password in the VPS secret manager first. The same value must be stored as `GEPG_CERTIFICATE_PASSWORD`. If your secret manager has no generator, run this on a private admin shell and store the output immediately:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Do not reuse a password that has been exposed in chat or documentation.

```python
from getpass import getpass
from pathlib import Path

from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    pkcs12,
)

source = Path(input("Source PFX path: ").strip())
destination = Path(input("New PFX path: ").strip())
old_password = getpass("Current PFX password: ")
new_password = getpass("New PFX password from the secret manager: ")
confirmation = getpass("Confirm new PFX password: ")
if not new_password or new_password != confirmation:
    raise SystemExit("New passwords are empty or do not match.")

key, certificate, chain = pkcs12.load_key_and_certificates(
    source.read_bytes(), old_password.encode("utf-8")
)
if key is None or certificate is None:
    raise SystemExit("The source PFX does not contain its signing key and certificate.")

destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_bytes(
    pkcs12.serialize_key_and_certificates(
        b"GePG signing identity",
        key,
        certificate,
        chain,
        BestAvailableEncryption(new_password.encode("utf-8")),
    )
)
destination.chmod(0o600)

check_key, check_certificate, _ = pkcs12.load_key_and_certificates(
    destination.read_bytes(), new_password.encode("utf-8")
)
if check_key is None or check_certificate is None:
    raise SystemExit("New PFX verification failed.")
print("New PFX created and verified; no password was printed.")
```

Run it with the backend's Python environment, which includes `cryptography`:

```sh
uv run python rewrap_gepg_pfx.py
```

Use the old PFX path as the source and the secure mounted path planned for the VPS as the destination, for example `/run/secrets/gepg/private.pfx`. Restrict the file to the backend service account. Remove the temporary script and source copy from staging after the transfer is verified; retain the original old-system PFX unchanged. Store the new PFX password only in the VPS secret manager.

## 3. Set production environment variables

Configure these values in the VPS service environment or secret manager. Prefer the platform's secret mechanism over a plain `.env` file. If the VPS requires an environment file, keep it outside the repository and restrict it to the service account.

| Variable | Production value |
| --- | --- |
| `SECRET_KEY` | Generate a unique Django secret using the command below. |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Comma-separated production hostnames/IPs served by Django; no scheme. |
| `TIME_ZONE` | `Africa/Dar_es_Salaam` |
| `DATABASE_URL` | The new system's production database URL from the VPS secret store. |
| `GEPG_SIMULATE` | `False` |
| `GEPG_BILL_CREATE_URL` | Exact old production bill-create URL. |
| `GEPG_BILL_CANCEL_URL` | Exact old production cancellation URL. |
| `GEPG_RECONCILIATION_URL` | Exact old production reconciliation URL. |
| `GEPG_SP_GRP_CODE`, `GEPG_SYS_CODE`, `GEPG_SP_CODE`, `GEPG_SUB_SP_CODE`, `GEPG_COLL_CENT_CODE`, `GEPG_GFS_CODE` | Exact old production service codes. |
| `GEPG_USE_DIGITAL_SIGNATURE` | `True` |
| `GEPG_CERTIFICATE_PASSWORD` | Password used to re-encrypt the new PFX copy. |
| `GEPG_PRIVATE_KEY_PATH` | Absolute VPS path to the mounted private PFX, e.g. `/run/secrets/gepg/private.pfx`. |
| `BEEM_AFRICA_API_KEY`, `BEEM_AFRICA_SECRET_KEY` | Existing Beem production credentials. |
| `AUTO_BILL_AFTER_IDENTIFICATION` | Set `True` only if production should automatically bill after the final stone is identified; otherwise `False`. |

Generate the Django secret from the backend directory and put the output directly into the secret manager:

```sh
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Do not generate new GePG URLs, service codes, or a new signing key locally. The callback paths are part of the existing registration and are listed in step 4.

## 4. Route the existing callback URLs to the VPS

The new backend exposes the old registered paths at the root of the site. Keep the existing GePG registration unchanged and configure DNS, firewall, reverse proxy, and TLS so those exact URLs reach the new backend:

```text
POST /billing/api/payments/notification/
POST /billing/api/bill/response/
POST /billing/api/bill/cancel-response/
POST /billing/reconciliation/response/
```

Use the existing public IP/domain expected by GePG. The TLS certificate and reverse-proxy rules must serve that host and preserve the paths exactly; do not add `/api/v1/`, rewrite them under `/gepg/`, or redirect them to the retired app. Permit GePG callback traffic to reach the new routes and permit the backend to make outbound connections to the copied GePG URLs and the Beem SMS endpoint.

## 5. Deploy and validate without live gateway calls

From the backend directory on the VPS, install the locked dependencies, check the production settings, and apply the new database migrations:

```sh
uv sync --frozen
uv run python manage.py check --deploy
uv run python manage.py migrate
```

Before enabling production traffic, validate the environment and signing identity in a staging deployment or controlled maintenance window. Run the local signing and mocked wire-contract tests; they do not call GePG:

```sh
uv run pytest apps/billing/tests/test_gepg_legacy.py -q
```

Confirm that `GEPG_SIMULATE` is false, signing is enabled, the configured PFX path exists and is readable by the service account, and the app can sign with the configured password. Do not verify credentials by printing environment values. Do not send a test bill, cancellation, or reconciliation to a live GePG URL as part of this checklist.

Only after these checks pass should the public host/IP route to the new service and the old application be stopped. Watch application logs and the new bill/payment records after cutover. Successful bill issuance should be confirmed through the normal registered GePG callback flow, not by a fabricated production notification.

## Production limits to account for

- No old bills, payments, or reconciliation records are migrated. A callback for an old bill absent from the new database receives `7102` and may be retried by GePG.
- Callback requests are CSRF-exempt and do not verify inbound signatures. `GEPG_PUBLIC_CERT_PATH` is not currently used for callback verification; protect the routes at the network edge and account for this limitation.
- Cancellation and reconciliation were ported from the old implementation, but the old cancellation code described its destination as a mock. Without a live gateway check, neither flow is verified against GePG production.
- A successful control-number SMS is recorded to prevent repeat sends. Beem delivery still depends on the credentials, customer phone number, and provider availability.
- The old system's unused bill-update URL is intentionally omitted because there is no caller in either configured workflow.
