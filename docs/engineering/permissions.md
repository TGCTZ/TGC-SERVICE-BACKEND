# Permissions

## The model

Plain Django. No `django-guardian`, no bespoke role tables.

- A **permission** is a `django.contrib.auth.Permission`, labelled
  `<app_label>.<codename>` - for example `catalog.view_product`.
- A **role** is a `django.contrib.auth.Group`.
- A user's effective permissions are the union of their groups' permissions
  plus any assigned directly.

Django creates four permissions per model automatically: `add_`, `change_`,
`delete_` and `view_`.

## The role matrix

`apps/users/roles.py` holds `ROLE_PERMISSIONS`, a dict of role name to
permission labels. `manage.py setup_roles` applies it and is safe to re-run.

| Role | Scope |
|---|---|
| `superadmin` | Every permission, resolved dynamically at run time |
| `admin` | Full CRUD on users and catalog, role management, audit read |
| `manager` | Full catalog CRUD, read-only on people, audit read |
| `editor` | Catalog add/change/view - no delete |
| `viewer` | Read-only across catalog and users |

`superadmin` is resolved as `Permission.objects.all()` rather than a literal
list, so a newly added model is covered without editing the file.

## Protected roles

`PROTECTED_ROLES` names roles the API refuses to rename, delete or re-scope.
`superadmin` is the escape hatch that repairs a broken permission setup, so
allowing it to be narrowed would let an administrator lock everyone out
irrecoverably. Enforced in `apps/users/services/roles.py`.

## Enforcement

`StrictModelPermissions` (in `apps/core/permissions.py`) extends DRF's
`DjangoModelPermissions` with one change that matters: it requires
`view_<model>` for `GET` and `HEAD`. DRF's stock class leaves reads wide open,
so any authenticated user with no permissions at all could otherwise read every
record in the system.

The `restore` action maps to `change_<model>` rather than a bespoke
`restore_<model>`. Restoring a row is a state change, and a dedicated permission
would have to be declared on every model in the project.

For checks outside a DRF view - a management command, a webhook - use
`require_permission(user, "catalog.change_product")`. A `None` user means a
trusted system caller and is allowed through deliberately.

## Module gates

Some permissions guard a whole UI section rather than a table: `module.user`,
`module.catalog`, `module.settings`, `module.audit`. They have no model of their
own, so they hang off `apps/core/models/gates.py` - an unmanaged model that
creates no table but does create permissions.

The same trick carries `audit.view_systemlog` in `apps/audit/models.py`.
