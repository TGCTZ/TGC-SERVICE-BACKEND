"""Role assignment, protection and hierarchy rules.

Two separate guards, because they answer different questions:

- **Protection** - may *anyone* change this role? ``superadmin`` is the escape
  hatch that fixes a broken permission setup, so no one may rename, narrow or
  delete it. A refusal is a 400: the request is wrong, not the requester.
- **Rank** - may *this* user change it? Everyone manages only roles, and the
  people holding them, ranked strictly below their own highest role (see
  ``ROLE_RANKS``). A refusal is a 403.

Rank alone would still leave one way up: a manager creating a role with
permissions the manager lacks, then handing it out. So a role can only gain
permissions its editor already holds.
"""

from rest_framework.exceptions import PermissionDenied

from django.contrib.auth.models import Group
from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.users.roles import BASE_RANK, PROTECTED_ROLES, ROLE_RANKS, TOP_RANK


def role_rank(name: str) -> int:
    """Where a role sits in the hierarchy; unlisted roles are at the base."""
    return ROLE_RANKS.get(name, BASE_RANK)


def user_rank(user) -> int:
    """The rank of a user's highest role. Django superusers are at the top.

    Reads ``groups.all()`` rather than a fresh query, so a list of users that
    prefetched its groups is ranked without one query per row.
    """
    if user.is_superuser:
        return TOP_RANK
    return max((role_rank(group.name) for group in user.groups.all()), default=0)


def rank_allows(actor_rank: int, rank: int) -> bool:
    """Whether someone at ``actor_rank`` may manage something at ``rank``.

    Strictly above it - or at the top, which manages everything, peers too:
    the break-glass accounts must be able to fix one another.
    """
    return actor_rank == TOP_RANK or actor_rank > rank


def hidden_role_names(actor) -> list[str]:
    """Ranked roles above ``actor``, which ``actor`` is not shown at all.

    Not merely read-only: a manager should not learn that ``admin`` exists, nor
    an admin ``superadmin``. The roles and users lists leave these out, and a
    name among them is answered as if it did not exist. Your own level stays
    visible - you hold it - just locked.
    """
    actor_rank = user_rank(actor)
    if actor_rank == TOP_RANK:
        return []
    return [name for name, rank in ROLE_RANKS.items() if rank > actor_rank]


def permission_labels(permissions) -> set[str]:
    """Permission rows as the ``app_label.codename`` labels ``has_perm`` takes."""
    return {f"{p.content_type.app_label}.{p.codename}" for p in permissions}


@transaction.atomic
def sync_user_roles(*, user, role_names: list[str], actor):
    """Replace a user's group membership with ``role_names``.

    Args:
        user: Whose roles to set.
        role_names: The complete new set of role names.
        actor: Who is asking; see :func:`assert_can_assign`.

    Raises:
        ServiceError: If any name is not a group ``actor`` may know about -
            hidden roles are reported as unknown, not as refused.
        PermissionDenied: If the change touches a role ``actor`` does not outrank.
    """
    groups = list(
        Group.objects.filter(name__in=role_names).exclude(
            name__in=hidden_role_names(actor)
        )
    )
    missing = set(role_names) - {group.name for group in groups}
    if missing:
        raise ServiceError(f"Unknown role(s): {', '.join(sorted(missing))}")
    assert_can_assign(
        actor,
        before={group.name for group in user.groups.all()},
        after={group.name for group in groups},
    )
    user.groups.set(groups)
    return user


def assert_role_mutable(group: Group) -> None:
    """Reject changes to a protected role, whoever asks.

    Raises:
        ServiceError: If the group is protected.
    """
    if group.name in PROTECTED_ROLES:
        raise ServiceError(f"The '{group.name}' role is protected and cannot be changed.")


def assert_can_manage_role(actor, group: Group, *, new_name: str | None = None) -> None:
    """Reject an edit or deletion of a role ``actor`` does not outrank.

    Both names are checked on a rename: otherwise a role could be renamed to
    ``admin`` and take the rank with it.

    Raises:
        ServiceError: If the role is protected.
        PermissionDenied: If ``actor`` is not ranked above the role.
    """
    assert_role_mutable(group)
    for name in {group.name, new_name} - {None}:
        assert_can_create_role(actor, name)


def assert_can_create_role(actor, name: str) -> None:
    """Reject a role name that would rank at or above ``actor``.

    Raises:
        PermissionDenied: If the name ranks at or above ``actor``.
    """
    if not rank_allows(user_rank(actor), role_rank(name)):
        raise PermissionDenied(f"Only a role ranked above '{name}' can manage it.")


def assert_can_grant(actor, *, before: set[str], after: set[str]) -> None:
    """Reject giving a role permissions its editor does not hold.

    Only what is being *added* is checked. A role keeps whatever it already
    had, so a manager can still adjust a receptionist's role without holding
    the receptionist's notification subscriptions.

    Raises:
        PermissionDenied: Naming the permissions ``actor`` cannot grant.
    """
    beyond = sorted((after - before) - actor.get_all_permissions())
    if beyond:
        raise PermissionDenied(
            f"You cannot grant permissions you do not hold: {', '.join(beyond)}."
        )


def assert_can_assign(actor, *, before: set[str], after: set[str]) -> None:
    """Reject giving or taking away a role ``actor`` does not outrank.

    Only the change is checked, so saving a user whose roles are untouched is
    never refused on their account - and taking a role away needs the same
    rank as handing it out, so no one can strip a superior.

    Raises:
        PermissionDenied: Naming the roles ``actor`` cannot assign.
    """
    actor_rank = user_rank(actor)
    blocked = sorted(
        name for name in before ^ after if not rank_allows(actor_rank, role_rank(name))
    )
    if blocked:
        raise PermissionDenied(
            f"Only a role ranked above {', '.join(blocked)} can assign or remove it."
        )


def assert_can_manage_user(actor, target) -> None:
    """Reject editing or deleting an account ranked at or above ``actor``.

    Your own account is the exception - its roles stay guarded by
    :func:`assert_can_assign`, so editing yourself cannot raise you.

    Raises:
        PermissionDenied: If ``target`` ranks at or above ``actor``.
    """
    if actor.pk == target.pk:
        return
    if not rank_allows(user_rank(actor), user_rank(target)):
        raise PermissionDenied(
            "Only someone ranked above this user can change their account."
        )
