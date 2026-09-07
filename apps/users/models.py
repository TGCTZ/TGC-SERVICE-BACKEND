"""User model and its supporting lookups.

The custom user is defined on day one, before the first migration is ever run.
Swapping ``AUTH_USER_MODEL`` afterwards means unpicking foreign keys across
every table in the project, so this is effectively a one-time decision.
"""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.core.models import BaseModel, ReferenceModel

from .managers import UserManager


class UserStatus(ReferenceModel):
    """Lifecycle state of an account, e.g. Active, Suspended, Pending."""

    class Meta(ReferenceModel.Meta):
        verbose_name_plural = "user statuses"


class Gender(ReferenceModel):
    """Self-described gender option, editable rather than hardcoded."""

    class Meta(ReferenceModel.Meta):
        pass


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Application user, authenticated by email address.

    Inherits ``BaseModel`` so accounts are soft-deleted like everything else:
    a removed user keeps their audit trail and foreign keys intact, and the
    default manager stops them from logging in.
    """

    first_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    phone_number = models.CharField(max_length=50, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_number = models.CharField(max_length=50, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.ForeignKey(
        Gender, on_delete=models.SET_NULL, null=True, blank=True, related_name="users"
    )
    user_status = models.ForeignKey(
        UserStatus,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    locale = models.CharField(max_length=10, default="en")

    last_login_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()
    all_objects = models.Manager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.full_name or self.email

    @property
    def full_name(self) -> str:
        """First, middle and last name joined, skipping the blanks."""
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part).strip()

    def get_full_name(self) -> str:
        """Django admin hook; delegates to ``full_name``."""
        return self.full_name

    def get_short_name(self) -> str:
        """Django admin hook."""
        return self.first_name


class IdentityDetail(BaseModel):
    """Government or institutional identity document attached to a user."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="identity_detail"
    )
    id_type = models.CharField(max_length=100)
    id_number = models.CharField(max_length=100)
    id_document = models.FileField(upload_to="identity/", null=True, blank=True)
    issue_country = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.id_type} - {self.id_number}"
