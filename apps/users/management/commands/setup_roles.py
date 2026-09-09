"""Create or update the groups described by ``apps.users.roles``."""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import ModuleGate
from apps.users.roles import ROLE_PERMISSIONS


class Command(BaseCommand):
    """Sync Django groups with the role matrix. Safe to run repeatedly."""

    help = "Create/update auth groups from apps.users.roles.ROLE_PERMISSIONS."

    def add_arguments(self, parser):
        """Pruning is opt-in because it removes rows, including memberships."""
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Delete groups and module gates the code no longer declares.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        """Reconcile every declared role, reporting what changed."""
        for role, labels in ROLE_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=role)

            if role == "superadmin":
                # Resolved dynamically so new models are covered automatically.
                permissions = list(Permission.objects.all())
            else:
                permissions = self._resolve(labels)

            group.permissions.set(permissions)
            verb = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"{verb} '{role}' with {len(permissions)} permissions")
            )

        self._reconcile_stale(prune=options["prune"])

    def _resolve(self, labels):
        """Turn ``app_label.codename`` strings into Permission rows.

        Unknown labels are reported rather than raising: a role may legitimately
        reference an app that has not been migrated yet in a partial deployment.
        """
        resolved = []
        for label in labels:
            app_label, codename = label.split(".", 1)
            permission = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if permission is None:
                self.stderr.write(self.style.WARNING(f"  unknown permission: {label}"))
                continue
            resolved.append(permission)
        return resolved

    def _reconcile_stale(self, *, prune: bool):
        """Report - and optionally remove - rows the code no longer declares.

        Groups and module gates outlive the code that created them: renaming a
        role leaves the old group behind, still granting whatever it granted,
        and shrinking ``ModuleGate.Meta.permissions`` leaves the retired gate in
        ``auth_permission``. Neither is visible in a diff, so the command that
        claims to bring an environment back in line has to say so.
        """
        stale_groups = Group.objects.exclude(name__in=ROLE_PERMISSIONS)
        declared_gates = {codename for codename, _ in ModuleGate._meta.permissions}
        stale_gates = Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(ModuleGate),
            codename__startswith="module_",
        ).exclude(codename__in=declared_gates)

        for group in stale_groups:
            members = group.user_set.count()
            if prune:
                group.delete()
                self.stdout.write(
                    self.style.WARNING(
                        f"Deleted stale role '{group.name}' ({members} members)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Stale role '{group.name}' ({members} members) - "
                        f"run with --prune to remove"
                    )
                )

        for permission in stale_gates:
            if prune:
                permission.delete()
                self.stdout.write(
                    self.style.WARNING(f"Deleted stale gate '{permission.codename}'")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Stale module gate '{permission.codename}' - "
                        f"run with --prune to remove"
                    )
                )
