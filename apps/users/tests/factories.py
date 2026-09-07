"""Factories for the users app.

Shared with the ``seed_demo`` management command so demo data and test data
never drift apart.
"""

import factory
from factory.django import DjangoModelFactory

from apps.users.models import Gender, IdentityDetail, User, UserStatus


class UserStatusFactory(DjangoModelFactory):
    """Account lifecycle state."""

    class Meta:
        model = UserStatus
        django_get_or_create = ("name",)  # keeps re-seeding idempotent

    name = factory.Iterator(["Active", "Suspended", "Pending", "Archived"])


class GenderFactory(DjangoModelFactory):
    """Gender option."""

    class Meta:
        model = Gender
        django_get_or_create = ("name",)

    name = factory.Iterator(["Female", "Male", "Non-binary", "Prefer not to say"])


class UserFactory(DjangoModelFactory):
    """An application user with a usable password."""

    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    is_active = True
    city = factory.Faker("city")
    country = factory.Faker("country")

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """Hash a password so the account can actually authenticate."""
        if not create:
            return
        self.set_password(extracted or "TestPass!2026")
        self.save(update_fields=["password"])


class IdentityDetailFactory(DjangoModelFactory):
    """Identity document for a user."""

    class Meta:
        model = IdentityDetail

    user = factory.SubFactory(UserFactory)
    id_type = factory.Iterator(["Passport", "National ID", "Driving Licence"])
    id_number = factory.Faker("bothify", text="??######")
    issue_country = factory.Faker("country")
