# Permissions

Plain Django `Group` and `Permission`. No custom role tables, no `django-guardian`.

## Resolution

```mermaid
flowchart TD
    U["User"] --> G["Groups<br/><i>a role is a Group</i>"]
    U --> DIRECT["user_permissions<br/><i>direct grants, rarely used</i>"]
    G --> GP["Group permissions"]
    GP --> EFF["Effective permission set"]
    DIRECT --> EFF

    EFF --> SUPER{"is_superuser?"}
    SUPER -->|yes| ALL["every permission,<br/>checks bypassed entirely"]
    SUPER -->|no| EFF2["the union above"]

    style U stroke:#4d90d9,stroke-width:2px
    style SUPER stroke:#d99a2b,stroke-width:2px
    style ALL stroke:#3fa860,stroke-width:2px
```

## Method to permission

`StrictModelPermissions` in `apps/core/permissions.py`:

```mermaid
flowchart TD
    REQ["Incoming request"] --> M{"HTTP method"}

    M -->|"GET or HEAD"| VIEW["app.view_model"]
    M -->|POST| ADD["app.add_model"]
    M -->|"PUT or PATCH"| CHANGE["app.change_model"]
    M -->|DELETE| DEL["app.delete_model"]
    M -->|OPTIONS| NONE["no permission required"]

    VIEW --> HAS{"user holds it?"}
    ADD --> HAS
    CHANGE --> HAS
    DEL --> HAS

    HAS -->|yes| ALLOW(["proceed to the view"])
    HAS -->|no| DENY(["403 Forbidden"])
    NONE --> ALLOW

    style M stroke:#d99a2b,stroke-width:2px
    style HAS stroke:#d99a2b,stroke-width:2px
    style ALLOW stroke:#3fa860,stroke-width:2px
    style DENY stroke:#d9534f,stroke-width:2px
    style VIEW stroke:#4d90d9,stroke-width:2px
```

The `GET` row is the whole reason this class exists. DRF's stock
`DjangoModelPermissions` maps `GET` to **no permission at all**, so any
authenticated user — including one with an empty role — could read every record.
Requiring `view_<model>` closes that hole, and
`test_user_without_permissions_cannot_even_read` pins the behaviour.

`restore` maps to `change_<model>`: bringing a row back is a state change, and a
dedicated `restore_<model>` would have to be declared on every model in the
project for no real gain.

## Roles

Defined in code at `apps/users/roles.py`, applied by `manage.py setup_roles`,
which is idempotent and safe to re-run.

```mermaid
flowchart LR
    CODE["ROLE_PERMISSIONS<br/><b>apps/users/roles.py</b>"] --> CMD["manage.py setup_roles"]
    CMD --> RESOLVE{"which role?"}
    RESOLVE -->|superadmin| DYN["Permission.objects.all()<br/><i>resolved at run time</i>"]
    RESOLVE -->|others| LIT["literal label list"]
    DYN --> GROUPS[("auth_group<br/>+ auth_group_permissions")]
    LIT --> GROUPS

    style CODE stroke:#4d90d9,stroke-width:2px
    style RESOLVE stroke:#d99a2b,stroke-width:2px
    style GROUPS stroke:#3fa860,stroke-width:2px
```

| Role | Scope |
| --- | --- |
| `superadmin` | Every permission, resolved dynamically |
| `administrator` | Full CRUD across the domain, users, roles, audit read |
| `receptionist` | Customers and orders; registers and types stones |
| `editor` | Catalog add / change / view — no delete |
| `accountant` | Bills, payments, service providers, and pricing |

Keeping the matrix in code rather than in seed data means a role change arrives
as a reviewable diff.

## Protected roles

```mermaid
flowchart TD
    REQ(["PUT or DELETE /api/v1/roles/{id}/"]) --> CHECK{"name in<br/>PROTECTED_ROLES?"}
    CHECK -->|yes| ERR(["400<br/>ServiceError: role is protected"])
    CHECK -->|no| PROCEED(["apply the change"])

    style REQ stroke:#4d90d9,stroke-width:2px
    style CHECK stroke:#d99a2b,stroke-width:2px
    style PROCEED stroke:#3fa860,stroke-width:2px
    style ERR stroke:#d9534f,stroke-width:2px
```

`superadmin` is the escape hatch that repairs a broken permission setup. Letting
it be renamed, deleted or narrowed would allow an administrator to lock everyone
out of the system irrecoverably.

## Module gates

Four permissions guard whole UI sections rather than tables: `module_user`,
`module_orders`, `module_billing`, `module_settings`, `module_audit`. They have no table of their
own, so they hang off an **unmanaged** model.

```mermaid
flowchart LR
    GATE["ModuleGate<br/><b>apps/core/models/gates.py</b><br/>managed = False<br/>default_permissions = ()"]
    GATE --> NOTABLE["no migration creates a table"]
    GATE --> PERMS[("auth_permission rows<br/>are still created")]
    PERMS --> UI["client shows or hides<br/>a navigation section"]

    style GATE stroke:#4d90d9,stroke-width:2px
    style PERMS stroke:#3fa860,stroke-width:2px
```

Django creates permission rows for unmanaged models too, which is precisely what
makes this work. The same trick carries `audit.view_systemlog` in
`apps/audit/models.py`.
