"""The role-to-permission matrix, defined in code.

Keeping this as a literal dict rather than database seed data means role changes
show up in code review as a diff, and ``manage.py setup_roles`` can be re-run at
any time to bring an environment back in line.

Roles map onto Django ``Group`` rows; the strings are permission labels in
``<app_label>.<codename>`` form.
"""

CRUD = ("add", "change", "delete", "view")
READ = ("view",)

USER_MODELS = ("user", "userstatus", "gender", "identitydetail")
CATALOG_MODELS = (
    "product",
    "productimage",
    "productcategory",
    "brand",
    "productstatus",
    "unitofmeasure",
    "tag",
)


def _perms(app_label: str, models: tuple[str, ...], actions: tuple[str, ...]):
    """Expand an app, its models and a set of actions into permission labels."""
    return [f"{app_label}.{action}_{model}" for model in models for action in actions]


# Coarse gates controlling whether a whole UI section is reachable.
MODULE_GATES = {
    "user": "core.module_user",
    "catalog": "core.module_catalog",
    "settings": "core.module_settings",
    "audit": "core.module_audit",
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Full access. Also granted every permission dynamically by setup_roles, so
    # new models are covered without editing this file.
    "superadmin": [],
    "admin": (
        _perms("users", USER_MODELS, CRUD)
        + _perms("catalog", CATALOG_MODELS, CRUD)
        + ["auth.view_group", "auth.add_group", "auth.change_group", "auth.delete_group"]
        + ["auth.view_permission", "auditlog.view_logentry"]
        + list(MODULE_GATES.values())
    ),
    "manager": (
        _perms("catalog", CATALOG_MODELS, CRUD)
        + _perms("users", USER_MODELS, READ)
        + ["auditlog.view_logentry"]
        + [MODULE_GATES["catalog"], MODULE_GATES["user"], MODULE_GATES["audit"]]
    ),
    "editor": [
        *_perms("catalog", CATALOG_MODELS, ("add", "change", "view")),
        MODULE_GATES["catalog"],
    ],
    "viewer": (
        _perms("catalog", CATALOG_MODELS, READ)
        + _perms("users", USER_MODELS, READ)
        + [MODULE_GATES["catalog"], MODULE_GATES["user"]]
    ),
}

# Roles the API refuses to rename, delete or re-scope. Without this, a
# privileged user could narrow superadmin and lock everyone out irrecoverably.
PROTECTED_ROLES = frozenset({"superadmin"})
