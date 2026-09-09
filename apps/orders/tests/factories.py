"""Factories for the order domain.

Reused by ``manage.py seed``, so the shapes here are the shapes a developer
sees on a freshly seeded database.
"""

import factory
from factory.django import DjangoModelFactory

from apps.gems.enums import StoneStatus, WeightUnit
from apps.gems.tests.factories import StoneTypeFactory
from apps.orders.models import Customer, Order, Stone


class CustomerFactory(DjangoModelFactory):
    """A submitting customer."""

    class Meta:
        model = Customer
        django_get_or_create = ("phone",)

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    phone = factory.Sequence(lambda n: f"2557{n:08d}")
    email = factory.Faker("email")
    region = factory.Faker("city")


class OrderFactory(DjangoModelFactory):
    """An order.

    Built directly rather than through ``create_order`` so a test can pin the
    reference number; the service is exercised on its own.
    """

    class Meta:
        model = Order
        django_get_or_create = ("reference_number",)

    reference_number = factory.Sequence(lambda n: f"ORD-2026-{n:04d}")
    customer = factory.SubFactory(CustomerFactory)
    received_date = factory.Faker("date_this_year")
    stone_count = 3


class StoneFactory(DjangoModelFactory):
    """A registered stone."""

    class Meta:
        model = Stone

    order = factory.SubFactory(OrderFactory)
    label = factory.Sequence(lambda n: chr(65 + n % 26))
    stone_type = factory.SubFactory(StoneTypeFactory)
    weight = factory.Faker("pydecimal", left_digits=2, right_digits=3, positive=True)
    weight_unit = WeightUnit.CARAT
    status = StoneStatus.RECEIVED
