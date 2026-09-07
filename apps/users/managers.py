"""Manager for the custom user model."""

from django.contrib.auth.base_user import BaseUserManager

from apps.core.managers import SoftDeleteManager


class UserManager(SoftDeleteManager, BaseUserManager):
    """Combines soft-delete filtering with Django's user-creation helpers.

    The MRO matters: ``SoftDeleteManager`` comes first so ``get_queryset``
    excludes soft-deleted users, which is what keeps a deleted account from
    authenticating.
    """

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """Normalise, hash and persist. Shared by both public constructors."""
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Create a standard, non-privileged user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Create a user with full administrative access."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)
