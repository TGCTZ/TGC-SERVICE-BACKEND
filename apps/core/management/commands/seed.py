"""Populate an empty database with realistic demo data.

Reuses the ``factory_boy`` factories from each app's ``tests/factories.py``
rather than defining a second set of fixtures. One definition, two consumers:
the suite and this command can never disagree about what a valid row looks like.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

DEMO_PASSWORD = "1234567890"  # noqa: S105 - demo data, never a real credential

# Enough of a stone catalogue to exercise pricing, findings and certification.
# The lab's three pricing tiers and the flat fee each carries, in TZS.
STONE_CATEGORIES = (
    ("Precious", 30_000),
    ("Semi-precious", 10_000),
    ("Diamond", 40_000),
)

STONE_TYPES = (
    ("Ruby", "Precious"),
    ("Sapphire", "Precious"),
    ("Emerald", "Precious"),
    ("Diamond", "Diamond"),
    ("Tanzanite", "Semi-precious"),
    ("Garnet", "Semi-precious"),
    ("Tourmaline", "Semi-precious"),
    ("Spinel", "Semi-precious"),
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

# --history-months only: enough spread for the market statistics to have shape.
CHANNELS = ("CRDB Bank", "NMB Bank", "M-Pesa", "Tigo Pesa", "Airtel Money")
NATURE_WEIGHTS = (
    ("natural", 70),
    ("treated", 14),
    ("enhanced", 8),
    ("synthetic", 6),
    ("artificial", 2),
)
TREATMENT_WEIGHTS = (
    ("none", 55),
    ("heated", 28),
    ("oiled", 6),
    ("fracture_filled", 4),
    ("dyed", 3),
    ("irradiated", 2),
    ("impregnated", 1),
    ("bleached", 1),
)


def _weighted(pairs):
    """One value from ``(value, weight)`` pairs."""
    values, weights = zip(*pairs, strict=True)
    return random.choices(values, weights=weights)[0]


def _days(low, high):
    """A random duration between ``low`` and ``high`` days."""
    return timedelta(days=random.uniform(low, high))


class Command(BaseCommand):
    """Seed roles, users and the stone reference tables. Idempotent."""

    help = "Populate the database with demo data for local development."

    def add_arguments(self, parser):
        """Expose the volume knobs so a bigger dataset is one flag away."""
        parser.add_argument("--users", type=int, default=20)
        parser.add_argument("--orders", type=int, default=12)
        parser.add_argument(
            "--history-months",
            type=int,
            default=0,
            help="Spread the orders over this many past months and carry each "
            "as far through the pipeline as its age allows, so the management "
            "statistics have trends to show. 0 keeps every order in the present.",
        )

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
            StoneCategoryFactory,
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
        # The fee lives on the tier, so a ruby and a sapphire cost the same.
        categories = {
            name: StoneCategoryFactory(name=name, price=price)
            for name, price in STONE_CATEGORIES
        }
        for name, category in STONE_TYPES:
            StoneTypeFactory(name=name, category=categories[category])
        species_list = []
        varieties_of = {}
        for species_name, varieties in SPECIES_VARIETIES.items():
            species = SpeciesFactory(name=species_name)
            species_list.append(species)
            varieties_of[species.pk] = [
                VarietyFactory(name=variety_name, species=species)
                for variety_name in varieties
            ]
        colors = [ColorFactory(name=name, group=group) for name, group in COLORS]
        origins = [OriginFactory(name=name) for name in ORIGINS]
        for _ in range(5):
            ShapeCutFactory()
            InstrumentFactory()

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

        self.stdout.write("Creating the GePG service provider...")
        provider = ServiceProviderFactory(sp_code="SP001", name="TGC")

        stone_types = list(StoneType.objects.all())
        if options["history_months"]:
            self._seed_history(
                orders=options["orders"],
                months=options["history_months"],
                provider=provider,
                stone_types=stone_types,
                species_list=species_list,
                varieties_of=varieties_of,
                colors=colors,
                origins=origins,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Role accounts: <role>@example.com / {DEMO_PASSWORD}"
                )
            )
            return

        self.stdout.write(f"Creating {options['orders']} orders...")
        billed = 0
        for _ in range(options["orders"]):
            customer = CustomerFactory()
            stone_count = random.randint(1, 4)
            order = create_order(customer=customer, stone_count=stone_count)
            # A spread of progress, so every worklist has something in it on a
            # fresh database: some orders half-identified, some ready to bill,
            # some already billed and paid.
            identified = random.randint(0, stone_count)
            for _ in range(identified):
                add_stone(order, stone_type=random.choice(stone_types))
            if identified == stone_count and billed < 4:
                bill = generate_bill_for_order(order, service_provider=provider)
                billed += 1
                if billed <= 2:
                    simulate_payment(bill)
                    # Carry the first order all the way to a certificate, so the
                    # findings and certification queues both have
                    # content and at least one certificate exists.
                    for stone in order.stones.all():
                        stone.refresh_from_db()
                        # Weight is recorded at the bench, not at reception.
                        update_stone(
                            stone,
                            weight=Decimal(f"{random.uniform(0.5, 12):.3f}"),
                        )
                        # Species, colour, weight and conclusion are what
                        # `finalize_report` insists on, so a seeded report is
                        # complete enough to sign off and certify.
                        report = create_report(
                            stone=stone,
                            species=random.choice(species_list),
                            color=random.choice(colors),
                            origin=random.choice(origins),
                            conclusion="Seeded findings.",
                        )
                        if billed == 1:
                            finalize_report(report)
                            issue_certificate(stone)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Role accounts: <role>@example.com / {DEMO_PASSWORD}"
            )
        )

    def _seed_history(
        self,
        *,
        orders,
        months,
        provider,
        stone_types,
        species_list,
        varieties_of,
        colors,
        origins,
    ):
        """Orders spread over past months, each carried as far as its age allows.

        Every order gets a timeline - its stones identified within days, then
        billed, paid (or not: a few never are) and certified - and is taken
        through the real services only up to the stages whose moment has
        passed. The services stamp everything "now", so each row is then moved
        back onto its timeline. The statistics then see turnaround, trends and
        a live backlog rather than one very busy afternoon.
        """
        from apps.analytics.periods import local_date
        from apps.billing.dev import simulate_payment
        from apps.billing.models import Bill, Payment
        from apps.billing.services import generate_bill_for_order
        from apps.certificates.models import Certificate
        from apps.certificates.services import issue_certificate
        from apps.gems.enums import OrderHold, StoneStatus
        from apps.identification.models import IdentificationReport
        from apps.identification.services import create_report, finalize_report
        from apps.orders.models import Order, StatusHistory, Stone
        from apps.orders.services import add_stone, create_order, hold_order, update_stone
        from apps.orders.tests.factories import CustomerFactory

        self.stdout.write(f"Creating {orders} orders over the past {months} months...")
        now = timezone.now()
        customers = []

        for _ in range(orders):
            # Skewed towards the recent past, so the lab looks like it is growing
            # and the trend lines have somewhere to go.
            registered = now - timedelta(days=months * 30 * random.random() ** 1.6)
            if customers and random.random() < 0.35:
                customer = random.choice(customers)
            else:
                customer = CustomerFactory()
                customers.append(customer)

            stone_count = random.randint(1, 4)
            order = create_order(customer=customer, stone_count=stone_count)
            Order.objects.filter(pk=order.pk).update(
                created_at=registered, received_date=local_date(registered)
            )

            roll = random.random()
            if roll < 0.02:
                hold_order(order, status=OrderHold.CANCELLED, reason="Customer withdrew.")
                continue
            if roll < 0.05:
                hold_order(order, status=OrderHold.ON_HOLD, reason="Awaiting documents.")
                continue

            stones = []
            identified = sorted(registered + _days(0.1, 3) for _ in range(stone_count))
            for moment in identified:
                if moment > now:
                    break
                stone = add_stone(order, stone_type=random.choice(stone_types))
                Stone.objects.filter(pk=stone.pk).update(created_at=moment)
                StatusHistory.objects.filter(
                    stone=stone, to_status=StoneStatus.RECEIVED
                ).update(changed_at=moment)
                stones.append(stone)
            if len(stones) < stone_count:
                continue

            billed_at = identified[-1] + _days(0.05, 1.5)
            if billed_at > now:
                continue
            bill = generate_bill_for_order(order, service_provider=provider)
            Bill.objects.filter(pk=bill.pk).update(
                issued_at=billed_at,
                created_at=billed_at,
                expiry_at=F("expiry_at") + (billed_at - bill.issued_at),
            )
            StatusHistory.objects.filter(
                stone__in=stones, to_status=StoneStatus.BILLED
            ).update(changed_at=billed_at)

            # Most bills are settled within a week, a tail takes longer, and a
            # few are never paid - the outstanding and aging figures need them.
            wait = random.choices(
                [_days(0.1, 1), _days(1, 7), _days(7, 30), None], weights=[55, 30, 10, 5]
            )[0]
            if wait is None or billed_at + wait > now:
                continue
            paid_at = billed_at + wait
            simulate_payment(bill)
            Payment.objects.filter(bill=bill).update(
                trx_dt_tm=paid_at, created_at=paid_at, psp_name=random.choice(CHANNELS)
            )
            StatusHistory.objects.filter(
                stone__in=stones, to_status=StoneStatus.PAID
            ).update(changed_at=paid_at)

            for stone in stones:
                certified_at = paid_at + _days(0.5, 5)
                if certified_at > now:
                    continue
                stone.refresh_from_db()
                update_stone(stone, weight=Decimal(f"{random.uniform(0.5, 12):.3f}"))
                species = random.choice(species_list)
                report = create_report(
                    stone=stone,
                    species=species,
                    variety=random.choice(varieties_of[species.pk]),
                    color=random.choice(colors),
                    origin=random.choice(origins),
                    nature_type=_weighted(NATURE_WEIGHTS),
                    treatment=_weighted(TREATMENT_WEIGHTS),
                    conclusion="Seeded findings.",
                )
                finalize_report(report)
                issue_certificate(stone)
                IdentificationReport.objects.filter(pk=report.pk).update(
                    created_at=paid_at, identified_at=certified_at - timedelta(hours=2)
                )
                Certificate.objects.filter(stone=stone).update(
                    issued_at=certified_at, created_at=certified_at
                )
                StatusHistory.objects.filter(
                    stone=stone, to_status=StoneStatus.CERTIFIED
                ).update(changed_at=certified_at)
