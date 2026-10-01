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

There are six roles. Four mirror the lab's stations - the back office, the front
desk, the bench and accounts - so each maps onto a stage of the stone's journey.
Two sit above them to run the system. Who may manage whom is set by rank; see
[The hierarchy](#the-hierarchy).

| Role | Station | Scope |
|---|---|---|
| `superadmin` | - | Every permission, resolved dynamically at run time |
| `admin` | - | Every permission by default, like `superadmin`, one rank below it |
| `manager` | Back office | Full CRUD across the domain, users, roles, audit |
| `receptionist` | Front desk | Customers, orders, handover. Does **not** identify stones |
| `gemmologist` | The bench | Both identification stages, finalize, and issuing certificates |
| `accountant` | Accounts | Bills, payments, service providers, and pricing |

`orders.add_stone` is Django's automatic `add_<model>` permission for `Stone`.
It is named after the row it creates, not the stage it serves - that stage is
**identification**, and it belongs to the bench, not to reception.

`superadmin` and `admin` (`FULL_ACCESS_ROLES`) are resolved as
`Permission.objects.all()` rather than a literal list, so a newly added model is
covered without editing the file. Neither is a station: `superadmin` is the
break-glass account, `admin` runs the system under it. The one exclusion is the
notification subscriptions below.

`setup_roles` resets every declared role to the code, `admin` included - a
superadmin who narrows `admin` on the roles screen will see it widened again the
next time the command runs.

### Notification subscriptions

A permission to *act* is not the same as the work *waiting on* you. Manager and
superadmin hold every workflow action so they can step in anywhere, and if the
pipeline's notifications went to everyone holding the action, they would hear
about every handoff in the lab while being the next step for none of it.

So each `NotificationKind` has its own opt-in permission,
`notifications.receive_<kind>`, and `notify_subscribers()` sends only to holders
of that. `roles.py` grants each one to the desk that is next:

| Subscription | Granted to |
|---|---|
| `receive_order_received` | `gemmologist` |
| `receive_ready_to_bill` | `accountant` |
| `receive_bill_paid` | `gemmologist` |
| `receive_ready_to_certify` | `gemmologist` |
| `receive_ready_for_collection` | `receptionist` |

`manager` holds none, and `setup_roles` withholds them from `superadmin`. They
are ordinary permissions, so a manager who does come to own a desk can be given
one from the roles screen. Because they follow any role held, a user who is
both manager and gemmologist still hears as the bench.

### Pricing is the stone catalogue

Django permissions are per-model, and the identification fee is a column on
`StoneCategory`. Changing a price therefore means holding
`gems.change_stonecategory`, which also lets the holder rename a category.

Grouping the fee with the catalogue rather than with billing is deliberate: a
price is reference data the lab maintains, not a figure an accountant sets per
bill. But it does mean the permission to set a price is the permission to edit
the category. If that separation matters later, expose price through a dedicated
action gated on a custom permission rather than splitting the model.

> ⚠️ The `accountant` role currently grants `gems.change_stonetype`, not
> `gems.change_stonecategory`. Since the fee lives on the category, the role
> that owns pricing cannot presently change a price. Treat this as an open
> defect rather than a documented rule.

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

## The hierarchy

`ROLE_RANKS` orders the roles: `superadmin` 100, `admin` 90, `manager` 50, and
every other role - the stations and any role made on the roles screen - 10. A
user's rank is that of their highest role (a Django superuser is 100; no role
at all is 0). Everyone manages only what ranks **strictly below** them:

| Rule | Why |
|---|---|
| Edit, rename or delete a role only below your rank; a rename checks the new name too | No widening your own role, and no renaming a role to `admin` to take its rank |
| Give or take away a role only below your rank | No promoting yourself or a peer, and no stripping a superior |
| Edit or delete an account only below your rank, or your own | No resetting a superior's email or deactivating them |
| A role gains only permissions its editor holds | No building a role above yourself and handing it out |

`superadmin` is the exception at the top: it manages everything, other
superadmins included, so the break-glass accounts can repair one another. Its
own role stays protected even from itself. So only a superadmin may edit,
delete or assign `admin`, and managers no longer edit the `manager` role or make
managers - admins do.

Protection answers "may anyone change this?" (a 400); rank answers "may *you*?"
(a 403). The role and user serializers expose `can_manage` / `can_assign` so the
screens hide what the API would refuse.

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
| `POST /orders/{id}/stones/` | `orders.add_stone` |
| `GET /orders/worklist/` | `orders.add_stone` |
| `POST /orders/{id}/hold/` | `orders.hold_order` |
| `POST /orders/{id}/release/` | `orders.hold_order` |
| `POST /stones/{id}/transition/` | `orders.transition_stone` |
| `GET /identification-reports/worklist/` | `identification.add_identificationreport` |
| `POST /identification-reports/{id}/finalize/` | `identification.finalize_report` |
| `GET /identification-reports/gemmologist-candidates/` | `identification.finalize_report` |
| `GET /bills/worklist/` | `billing.generate_bill` |
| `GET /bills/preview/` | `billing.generate_bill` |
| `POST /bills/generate/` | `billing.generate_bill` |
| `POST /bills/{id}/simulate-payment/` | `billing.generate_bill` *(development only)* |
| `GET /certificates/worklist/` | `certificates.issue_certificate` |
| `POST /certificates/` | `certificates.issue_certificate` |
| `POST /certificates/{id}/revoke/` | `certificates.revoke_certificate` |
| `GET /certificates/{id}/pdf/` | `certificates.view_certificate` *(method map)* |

`pdf` is deliberately absent from `action_permissions`: it is a **read** of data
the detail endpoint already returns in full, so the method-map fallback gives it
`view_certificate` and no role needs a new grant. Bespoke permissions are
reserved for verbs that change state — issuing, revoking, transitioning — where
"may read this" and "may do this" genuinely differ.

## Module gates

Some permissions guard a whole UI section rather than a table: `module_orders`,
`module_identification`, `module_billing`, `module_certificates`,
`module_reference`, `module_user`, `module_settings`, `module_audit`. They have
no model of their own, so they hang off `apps/core/models/gates.py` - an
unmanaged model that creates no table but does create permissions.

The gates are **presentation only**: the frontend hides a sidebar group (or an
Administration section) whose gate the user lacks, on top of each item's own
model permission. No endpoint checks them, so a hidden page still opens from a
direct link - access control stays with the model permissions. Unticking a gate
on the roles screen is how an admin tidies a role's navigation without stripping
the permissions its pages need.

The same unmanaged-model trick carries `audit.view_systemlog`
(`apps/audit/models.py`) and `analytics.view_statistics`
(`apps/analytics/models.py`); unlike the gates, both are enforced by their
endpoints.
