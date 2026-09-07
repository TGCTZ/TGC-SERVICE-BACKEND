"""Populate an empty database with realistic demo data.

Reuses the ``factory_boy`` factories from each app's ``tests/factories.py``
rather than defining a second set of fixtures. One definition, two consumers:
the suite and this command can never disagree about what a valid row looks like.
"""

import random

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

DEMO_PASSWORD = "DemoPass!2026"  # noqa: S105 - demo data, never a real credential


class Command(BaseCommand):
    """Seed lookups, role accounts, users and products. Idempotent."""

    help = "Populate the database with demo data for local development."

    def add_arguments(self, parser):
        """Expose the volume knobs so a bigger dataset is one flag away."""
        parser.add_argument("--users", type=int, default=20)
        parser.add_argument("--products", type=int, default=50)

    @transaction.atomic
    def handle(self, *args, **options):
        """Run every seeding stage in dependency order."""
        from apps.catalog.tests.factories import (
            BrandFactory,
            ProductCategoryFactory,
            ProductFactory,
            ProductStatusFactory,
            TagFactory,
            UnitOfMeasureFactory,
        )
        from apps.users.tests.factories import (
            GenderFactory,
            IdentityDetailFactory,
            UserFactory,
            UserStatusFactory,
        )

        self.stdout.write("Ensuring roles exist...")
        call_command("setup_roles", verbosity=0)

        self.stdout.write("Creating lookups...")
        statuses = [UserStatusFactory() for _ in range(4)]
        genders = [GenderFactory() for _ in range(4)]
        categories = [ProductCategoryFactory() for _ in range(6)]
        brands = [BrandFactory() for _ in range(5)]
        product_statuses = [ProductStatusFactory() for _ in range(3)]
        units = [UnitOfMeasureFactory() for _ in range(4)]
        tags = [TagFactory() for _ in range(8)]

        self.stdout.write("Creating one account per role...")
        for role in Group.objects.all():
            account = UserFactory(
                email=f"{role.name}@example.com",
                username=role.name,
                first_name=role.name.title(),
                last_name="Demo",
                password=DEMO_PASSWORD,
                user_status=statuses[0],
            )
            account.groups.set([role])
            if role.name == "superadmin":
                account.is_staff = True
                account.is_superuser = True
                account.save(update_fields=["is_staff", "is_superuser"])

        self.stdout.write(f"Creating {options['users']} users...")
        for _ in range(options["users"]):
            account = UserFactory(
                user_status=random.choice(statuses),
                gender=random.choice(genders),
            )
            if random.random() < 0.4:
                IdentityDetailFactory(user=account)

        self.stdout.write(f"Creating {options['products']} products...")
        for _ in range(options["products"]):
            product = ProductFactory(
                product_category=random.choice(categories),
                brand=random.choice(brands),
                product_status=random.choice(product_statuses),
                unit_of_measure=random.choice(units),
                is_featured=random.random() < 0.2,
            )
            product.tags.set(random.sample(tags, k=random.randint(0, 3)))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Role accounts: <role>@example.com / {DEMO_PASSWORD}"
            )
        )
