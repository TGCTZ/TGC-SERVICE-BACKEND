"""Create or update the groups described by ``apps.users.roles``."""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.users.roles import ROLE_PERMISSIONS


class Command(BaseCommand):
    """Sync Django groups with the role matrix. Safe to run repeatedly."""

    help = "Create/update auth groups from apps.users.roles.ROLE_PERMISSIONS."

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
