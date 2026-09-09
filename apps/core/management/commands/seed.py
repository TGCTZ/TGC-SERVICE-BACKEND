"""Populate an empty database with realistic demo data.

Reuses the ``factory_boy`` factories from each app's ``tests/factories.py``
rather than defining a second set of fixtures. One definition, two consumers:
the suite and this command can never disagree about what a valid row looks like.
"""

import random
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

DEMO_PASSWORD = "1234567890"  # noqa: S105 - demo data, never a real credential

# Enough of a stone catalogue to exercise pricing, findings and certification.
STONE_TYPES = (
    ("Ruby", "precious"),
    ("Sapphire", "precious"),
    ("Emerald", "precious"),
    ("Diamond", "diamond"),
    ("Tanzanite", "semi_precious"),
    ("Garnet", "semi_precious"),
    ("Tourmaline", "semi_precious"),
    ("Spinel", "semi_precious"),
)

SPECIES_VARIETIES = {
    "Corundum": ("Ruby", "Blue sapphire", "Padparadscha"),
    "Beryl": ("Emerald", "Aquamarine", "Morganite"),
    "Zoisite": ("Tanzanite",),
    "Quartz": ("Amethyst", "Citrine"),
}

COLORS = (
    ("Red", "red_pink"),
    ("Pink", "red_pink"),
    ("Blue", "blue"),
    ("Green", "green"),
    ("Yellow", "orange_yellow"),
    ("Colourless", "white_grey_black"),
    ("Violet", "purple_violet"),
)

ORIGINS = ("Tanzania", "Madagascar", "Sri Lanka", "Myanmar", "Mozambique")


class Command(BaseCommand):
    """Seed roles, users and the stone reference tables. Idempotent."""

    help = "Populate the database with demo data for local development."

    def add_arguments(self, parser):
        """Expose the volume knobs so a bigger dataset is one flag away."""
        parser.add_argument("--users", type=int, default=20)
        parser.add_argument("--orders", type=int, default=12)

    @transaction.atomic
    def handle(self, *args, **options):
        """Run every seeding stage in dependency order."""
        from apps.billing.dev import simulate_payment
        from apps.billing.services import generate_bill_for_order
        from apps.billing.tests.factories import ServiceProviderFactory
        from apps.certificates.services import issue_certificate
        from apps.gems.models import StoneType
        from apps.gems.tests.factories import (
            ColorFactory,
            InstrumentFactory,
            OriginFactory,
            ShapeCutFactory,
            SpeciesFactory,
            StoneTypeFactory,
            VarietyFactory,
        )
        from apps.identification.services import create_report, finalize_report
        from apps.orders.services import add_stone, create_order, update_stone
        from apps.orders.tests.factories import CustomerFactory
        from apps.users.tests.factories import (
            GenderFactory,
            IdentityDetailFactory,
            UserFactory,
            UserStatusFactory,
        )

        self.stdout.write("Ensuring roles exist...")
        call_command("setup_roles", verbosity=0)

        self.stdout.write("Creating user lookups...")
        statuses = [UserStatusFactory() for _ in range(4)]
        genders = [GenderFactory() for _ in range(4)]

        self.stdout.write("Creating the stone reference tables...")
        for name, category in STONE_TYPES:
            # A realistic spread of fees, rounded to whole shillings.
            StoneTypeFactory(
                name=name,
                category=category,
                price=random.randrange(20_000, 150_000, 5_000),
            )
        for species_name, varieties in SPECIES_VARIETIES.items():
            species = SpeciesFactory(name=species_name)
            for variety_name in varieties:
                VarietyFactory(name=variety_name, species=species)
        colors = [ColorFactory(name=name, group=group) for name, group in COLORS]
        origins = [OriginFactory(name=name) for name in ORIGINS]
        for _ in range(5):
            ShapeCutFactory()
            InstrumentFactory()

        self.stdout.write("Creating one account per role...")
        for role in Group.objects.all():
            account = UserFactory(
                email=f"{role.name}@tgc.com",
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

        self.stdout.write("Creating the GePG service provider...")
        provider = ServiceProviderFactory(sp_code="SP001", name="TGC")

        self.stdout.write(f"Creating {options['orders']} orders...")
        stone_types = list(StoneType.objects.all())
        billed = 0
        for _ in range(options["orders"]):
            customer = CustomerFactory()
            stone_count = random.randint(1, 4)
            order = create_order(customer=customer, stone_count=stone_count)
            # A spread of progress, so every worklist has something in it on a
            # fresh database: some orders half-registered, some ready to bill,
            # some already billed and paid.
            registered = random.randint(0, stone_count)
            for _ in range(registered):
                add_stone(order, stone_type=random.choice(stone_types))
            if registered == stone_count and billed < 4:
                bill = generate_bill_for_order(order, service_provider=provider)
                billed += 1
                if billed <= 2:
                    simulate_payment(bill)
                    # Carry the first order all the way to a certificate, so the
                    # findings and certification queues both have content and at
                    # least one certificate exists to verify.
                    for stone in order.stones.all():
                        stone.refresh_from_db()
                        # Weight is recorded at the bench, not at reception.
                        update_stone(
                            stone,
                            weight=Decimal(f"{random.uniform(0.5, 12):.3f}"),
                        )
                        report = create_report(
                            stone=stone,
                            color=random.choice(colors),
                            origin=random.choice(origins),
                            conclusion="Seeded findings.",
                        )
                        if billed == 1:
                            finalize_report(report)
                            issue_certificate(stone)

        self.stdout.write(
            self.style.SUCCESS(f"Done. Role accounts: <role>@tgc.com / {DEMO_PASSWORD}")
        )
