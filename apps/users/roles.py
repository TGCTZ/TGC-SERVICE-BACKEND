"""The role-to-permission matrix, defined in code.

Keeping this as a literal dict rather than database seed data means role changes
show up in code review as a diff, and ``manage.py setup_roles`` can be re-run at
any time to bring an environment back in line.

Roles map onto Django ``Group`` rows; the strings are permission labels in
``<app_label>.<codename>`` form.

The four business roles mirror the lab's actual stations - reception, the
gemmology bench, accounts, and management - so each one maps onto a stage of
the stone's journey. Above them sit two roles that are not stations:

- ``admin`` runs the system: every permission by default, managers included in
  what it manages, but one rank below the top.
- ``superadmin`` is the break-glass account, and the only role that may edit,
  delete or hand out ``admin``.

Both are granted everything dynamically, so a newly added model is covered
without editing this file. Who may manage whom is set by :data:`ROLE_RANKS`.
"""


def _notified(*kinds: str) -> list[str]:
    """Subscriptions to the handoffs a desk is the next step for.

    Kept apart from the action permissions on purpose: holding a permission
    means a role *may* act, a subscription means the work is *waiting on* it.
    """
    return [f"notifications.receive_{kind}" for kind in kinds]


#: The bench. Named here so the identification app can ask "who is a
#: gemmologist?" without hardcoding a string that this file might rename.
GEMMOLOGIST_ROLE = "gemmologist"

CRUD = ("add", "change", "delete", "view")
READ = ("view",)

USER_MODELS = ("user", "userstatus", "gender", "identitydetail")
ORDERS_MODELS = ("customer", "order", "stone")
BILLING_MODELS = ("bill", "billitem", "payment", "serviceprovider")
IDENTIFICATION_MODELS = ("identificationreport", "instrumentused")
CERTIFICATE_MODELS = ("certificate",)
GEMS_MODELS = (
    "stonecategory",
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
    # new models are covered without editing this file - except notification
    # subscriptions: the break-glass account is not a desk any work waits on.
    "superadmin": [],
    # Everything by default, like superadmin - see FULL_ACCESS_ROLES - but one
    # rank below it: only a superadmin may edit, delete or assign this role, so
    # an admin can run the whole lab without reshaping the level above it.
    "admin": [],
    # Holds every workflow action so it can step in anywhere, and for that very
    # reason subscribes to no handoffs: it would hear about all the lab's work
    # and be the next step for none of it. Grant one from the roles screen if a
    # manager does come to own a desk.
    "manager": (
        _perms("users", USER_MODELS, CRUD)
        + _perms("gems", GEMS_MODELS, CRUD)
        + _perms("orders", ORDERS_MODELS, CRUD)
        + _perms("billing", BILLING_MODELS, CRUD)
        + _perms("identification", IDENTIFICATION_MODELS, CRUD)
        + _perms("certificates", CERTIFICATE_MODELS, CRUD)
        + ["orders.transition_stone", "orders.hold_order", "orders.view_statushistory"]
        + [
            "billing.generate_bill",
            "identification.finalize_report",
            *_perms("certificates", CERTIFICATE_MODELS, ("add", "view")),
            "certificates.issue_certificate",
            "certificates.revoke_certificate",
        ]
        + ["auth.view_group", "auth.add_group", "auth.change_group", "auth.delete_group"]
        + ["auth.view_permission", "auditlog.view_logentry", "audit.view_systemlog"]
        + ["analytics.view_statistics"]
        + list(MODULE_GATES.values())
    ),
    # Front desk: registers customers and their orders, and hands finished
    # certificates back. Identifying a stone is the bench's job, not reception's,
    # so `add_stone` and `change_stone` deliberately are not here - reception
    # records only how many stones arrived.
    "receptionist": [
        *_perms("gems", GEMS_MODELS, READ),
        *_perms("orders", ("customer", "order"), CRUD),
        "billing.view_bill",
        *_perms("orders", ("stone",), READ),
        # Pausing or withdrawing a visit is reception's call: the customer says
        # so at the desk, not at the bench.
        "orders.hold_order",
        # Kept: handover moves a stone to collected.
        "orders.transition_stone",
        "orders.view_statushistory",
        # Reception hands finished orders back, so it hears when one is ready.
        *_notified("ready_for_collection"),
        MODULE_GATES["orders"],
        MODULE_GATES["reference"],
    ],
    # The bench: identifies each stone's type (preliminary, which fixes the
    # price), then after payment records the findings against the
    # reference tables it reads.
    "gemmologist": [
        *_perms("gems", GEMS_MODELS, READ),
        *_perms("orders", ("order", "stone"), READ),
        "billing.view_bill",
        # Identification. Django names this permission after the row
        # it creates, not the stage it belongs to.
        "orders.add_stone",
        "orders.change_stone",
        "orders.transition_stone",
        *_perms("identification", IDENTIFICATION_MODELS, CRUD),
        "identification.finalize_report",
        *_perms("certificates", CERTIFICATE_MODELS, ("add", "view")),
        "certificates.issue_certificate",
        "orders.view_statushistory",
        # The bench is the next step three times: typing a new order's stones,
        # recording findings once paid, and certifying once finalized.
        *_notified("order_received", "bill_paid", "ready_to_certify"),
        # The orders module too: the preliminary queue and the stone it writes
        # both live under /orders/.
        MODULE_GATES["orders"],
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
        *_notified("ready_to_bill"),
        MODULE_GATES["billing"],
        MODULE_GATES["reference"],
    ],
}

# Roles the API refuses to rename, delete or re-scope. Without this, a
# privileged user could narrow superadmin and lock everyone out irrecoverably.
PROTECTED_ROLES = frozenset({"superadmin"})

# Roles setup_roles resolves to every permission rather than to a list, so a new
# model is covered without editing this file. Notification subscriptions are
# left out: neither role is a desk that work waits on.
FULL_ACCESS_ROLES = frozenset({"superadmin", "admin"})

# Who outranks whom. A user may manage - edit, delete, assign or take away, and
# manage the people holding - only roles ranked strictly below their own
# highest role, so no one can raise themselves or a peer. Superadmin is the top
# and manages everything, other superadmins included. Every role not listed -
# the stations, and any role created on the roles screen - sits at BASE_RANK;
# a user with no role at all is at 0.
ROLE_RANKS = {"superadmin": 100, "admin": 90, "manager": 50}
BASE_RANK = 10
TOP_RANK = ROLE_RANKS["superadmin"]
