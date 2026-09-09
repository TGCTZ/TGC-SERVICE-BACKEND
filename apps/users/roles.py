"""The role-to-permission matrix, defined in code.

Keeping this as a literal dict rather than database seed data means role changes
show up in code review as a diff, and ``manage.py setup_roles`` can be re-run at
any time to bring an environment back in line.

Roles map onto Django ``Group`` rows; the strings are permission labels in
``<app_label>.<codename>`` form.

The four business roles mirror the lab's actual stations - reception, the
gemmology bench, accounts, and administration - so each one maps onto a stage of
the stone's journey. ``superadmin`` is not a station; it is the break-glass
account, granted everything dynamically so a newly added model is covered
without editing this file.
"""

CRUD = ("add", "change", "delete", "view")
READ = ("view",)

USER_MODELS = ("user", "userstatus", "gender", "identitydetail")
ORDERS_MODELS = ("customer", "order", "stone")
BILLING_MODELS = ("bill", "billitem", "payment", "serviceprovider")
IDENTIFICATION_MODELS = ("identificationreport", "instrumentused")
CERTIFICATE_MODELS = ("certificate",)
GEMS_MODELS = (
    "stonetype",
    "species",
    "variety",
    "color",
    "origin",
    "shapecut",
    "instrument",
)


def _perms(app_label: str, models: tuple[str, ...], actions: tuple[str, ...]):
    """Expand an app, its models and a set of actions into permission labels."""
    return [f"{app_label}.{action}_{model}" for model in models for action in actions]


# Coarse gates controlling whether a whole UI section is reachable.
MODULE_GATES = {
    "orders": "core.module_orders",
    "identification": "core.module_identification",
    "billing": "core.module_billing",
    "certificates": "core.module_certificates",
    "reference": "core.module_reference",
    "user": "core.module_user",
    "settings": "core.module_settings",
    "audit": "core.module_audit",
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Full access. Also granted every permission dynamically by setup_roles, so
    # new models are covered without editing this file.
    "superadmin": [],
    "administrator": (
        _perms("users", USER_MODELS, CRUD)
        + _perms("gems", GEMS_MODELS, CRUD)
        + _perms("orders", ORDERS_MODELS, CRUD)
        + _perms("billing", BILLING_MODELS, CRUD)
        + _perms("identification", IDENTIFICATION_MODELS, CRUD)
        + _perms("certificates", CERTIFICATE_MODELS, CRUD)
        + ["certificates.view_certificateaccesslog"]
        + ["orders.transition_stone", "orders.view_statushistory"]
        + [
            "billing.generate_bill",
            "identification.finalize_report",
            *_perms("certificates", CERTIFICATE_MODELS, ("add", "view")),
            "certificates.issue_certificate",
            "certificates.view_certificateaccesslog",
            "certificates.issue_certificate",
            "certificates.revoke_certificate",
        ]
        + ["auth.view_group", "auth.add_group", "auth.change_group", "auth.delete_group"]
        + ["auth.view_permission", "auditlog.view_logentry", "audit.view_systemlog"]
        + list(MODULE_GATES.values())
    ),
    # Front desk: registers customers and their orders, and reads the stone
    # catalogue to type an incoming stone.
    "receptionist": [
        *_perms("gems", GEMS_MODELS, READ),
        *_perms("orders", ("customer", "order"), CRUD),
        "billing.view_bill",
        *_perms("orders", ("stone",), ("add", "change", "view")),
        "orders.transition_stone",
        "orders.view_statushistory",
        MODULE_GATES["orders"],
        MODULE_GATES["reference"],
    ],
    # The bench: records findings against the reference tables it reads.
    "gemmologist": [
        *_perms("gems", GEMS_MODELS, READ),
        *_perms("orders", ("order", "stone"), READ),
        "billing.view_bill",
        "orders.change_stone",
        "orders.transition_stone",
        *_perms("identification", IDENTIFICATION_MODELS, CRUD),
        "identification.finalize_report",
        *_perms("certificates", CERTIFICATE_MODELS, ("add", "view")),
        "certificates.issue_certificate",
        "certificates.view_certificateaccesslog",
        "orders.view_statushistory",
        MODULE_GATES["identification"],
        MODULE_GATES["reference"],
    ],
    # Accounts owns pricing. Because Django permissions are per-model and the
    # identification fee lives on StoneType, this also grants the right to edit
    # the rest of the stone-type row - see docs/engineering/permissions.md.
    "accountant": [
        *_perms("gems", GEMS_MODELS, READ),
        *_perms("orders", ORDERS_MODELS, READ),
        *_perms("billing", ("bill", "billitem", "payment"), READ),
        *_perms("billing", ("serviceprovider",), CRUD),
        "billing.generate_bill",
        "gems.change_stonetype",
        MODULE_GATES["billing"],
        MODULE_GATES["reference"],
    ],
}

# Roles the API refuses to rename, delete or re-scope. Without this, a
# privileged user could narrow superadmin and lock everyone out irrecoverably.
PROTECTED_ROLES = frozenset({"superadmin"})
