# Permissions

## The model

Plain Django. No `django-guardian`, no bespoke role tables.

- A **permission** is a `django.contrib.auth.Permission`, labelled
  `<app_label>.<codename>` - for example `gems.view_stonetype`.
- A **role** is a `django.contrib.auth.Group`.
- A user's effective permissions are the union of their groups' permissions
  plus any assigned directly.

Django creates four permissions per model automatically: `add_`, `change_`,
`delete_` and `view_`.

## The role matrix

`apps/users/roles.py` holds `ROLE_PERMISSIONS`, a dict of role name to
permission labels. `manage.py setup_roles` applies it and is safe to re-run.

The four business roles mirror the lab's actual stations, so each maps onto a
stage of the stone's journey and onto one of the four worklists.

| Role | Station | Scope |
|---|---|---|
| `superadmin` | - | Every permission, resolved dynamically at run time |
| `administrator` | Back office | Full CRUD across the domain, users, roles, audit |
| `receptionist` | Front desk | Customers and orders; registers and types stones |
| `gemmologist` | The bench | Findings, finalize, and issuing certificates |
| `accountant` | Accounts | Bills, payments, service providers, and pricing |

`superadmin` is resolved as `Permission.objects.all()` rather than a literal
list, so a newly added model is covered without editing the file. It is not a
station - it is the break-glass account.

### Pricing is the stone catalogue

Django permissions are per-model, and the identification fee is a column on
`StoneType`. So `accountant` holds `gems.change_stonetype`, which also lets them
rename and recategorise a stone type. The full-stack system kept price on its
own `StonePrice` table and could separate the two. If that separation matters
later, expose price through a dedicated action gated on a custom permission
rather than splitting the model again.

## Keeping the database in step

`setup_roles` reports groups and module gates the matrix no longer declares, and
removes them under `--prune`:

```bash
uv run python manage.py setup_roles --prune
```

Pruning is opt-in because it deletes group memberships. Without it a renamed
role leaves the old group behind, still granting whatever it granted, and a gate
dropped from `ModuleGate.Meta` stays in `auth_permission` where it keeps working
for anyone who already holds it. Neither shows up in a diff.

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

There is no bespoke `restore_<model>` permission - it would have to be declared
on every model in the project. `restore` is a `POST`, so it resolves to
`add_<model>` through the method map.

### Workflow verbs

`ActionPermissions` extends that class for custom `@action` routes. The method
map asks for `add_<model>` on every `POST`, but transitioning a stone, finalizing
a report and issuing a certificate are not creations - each has its own
permission declared on the model. Without this the four workflow permissions
would be decorative, and anyone holding `add_stone` could move a stone straight
to certified.

Declare the mapping on the ViewSet, keyed by action name:

```python
class StoneViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    action_permissions = {"transition": ["orders.transition_stone"]}
```

An action that is not listed falls back to the method map, so ordinary CRUD and
`restore` are unaffected.

| Action | Permission |
|---|---|
| `POST /stones/{id}/transition/` | `orders.transition_stone` |
| `POST /identification-reports/{id}/finalize/` | `identification.finalize_report` |
| `POST /bills/generate/` | `billing.generate_bill` |
| `POST /certificates/` | `certificates.issue_certificate` |
| `POST /certificates/{id}/revoke/` | `certificates.revoke_certificate` |

For checks outside a DRF view - a management command, a webhook - use
`require_permission(user, "gems.change_stonetype")`. A `None` user means a
trusted system caller and is allowed through deliberately.

## Module gates

Some permissions guard a whole UI section rather than a table: `module_orders`,
`module_identification`, `module_billing`, `module_certificates`,
`module_reference`, `module_user`, `module_settings`, `module_audit`. They have
no model of their
own, so they hang off `apps/core/models/gates.py` - an unmanaged model that
creates no table but does create permissions.

The same trick carries `audit.view_systemlog` in `apps/audit/models.py`.
