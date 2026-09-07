# Starting a new project from this template

## 1. Rename and reset

```bash
git clone <this-repo> my-project && cd my-project
rm -rf .git && git init
```

Update `name` and `description` in `pyproject.toml`, and `TITLE` in
`SPECTACULAR_SETTINGS` (`config/settings/base.py`).

## 2. Set up the environment

```bash
uv sync
cp .env.example .env
uv run python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Paste the key into `.env` and point `DATABASE_URL` at a fresh database.

## 3. Decide what to keep

| Keep | Why |
|---|---|
| `apps/core` | The whole point of the template. Rarely needs changes. |
| `apps/users` | Custom user, auth and RBAC. Adjust the profile fields to taste. |
| `apps/audit` | Useful in most projects, and hard to retrofit once you have data. |

`apps/catalog` is the worked example. If your domain is not products, delete
it - but read `models.py`, `views.py` and `services/product.py` first: they
demonstrate every pattern you will be repeating.

```bash
rm -rf apps/catalog
# then remove it from INSTALLED_APPS and config/urls.py,
# and drop CATALOG_MODELS from apps/users/roles.py
```

## 4. Edit the user model before migrating

This is the one irreversible step. `AUTH_USER_MODEL` cannot be swapped once
migrations have run without unpicking foreign keys across every table. Add,
remove or rename the fields on `apps/users/models.User` **now**.

Then delete the shipped migrations and generate your own:

```bash
rm apps/*/migrations/0*.py
uv run python manage.py makemigrations
uv run python manage.py migrate
```

## 5. Set up roles

Edit `ROLE_PERMISSIONS` in `apps/users/roles.py` for your domain, then:

```bash
uv run python manage.py setup_roles
uv run python manage.py createsuperuser
```

## 6. Build your first domain app

```bash
uv run python manage.py startapp orders apps/orders
```

Then, following `apps/catalog` as the reference:

1. Add `"apps.orders"` to `LOCAL_APPS` with its layer annotation.
2. Set `name = "apps.orders"` in its `AppConfig`.
3. Inherit `BaseModel` (or `ReferenceModel` for lookups) on every model.
4. Combine `BaseModelViewSet` with `ModelViewSet` and declare the four
   whitelists: `search_fields`, `filter_fields`, `ordering_fields`,
   `date_filter_fields`.
5. Register the router in `apps/orders/urls.py` and include it in `config/urls.py`.
6. Add the model's permissions to `ROLE_PERMISSIONS`.
7. Write factories and tests.

## 7. Checklist before your first commit

- [ ] `SECRET_KEY` is in `.env`, not in code
- [ ] `.env` is git-ignored, `.env.example` is committed
- [ ] `uv run pre-commit install` has been run
- [ ] `uv run pytest` is green
- [ ] `uv run ruff check . && uv run ruff format --check .` is clean
- [ ] The CI workflow points at your default branch
