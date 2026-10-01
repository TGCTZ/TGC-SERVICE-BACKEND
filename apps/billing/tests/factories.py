"""Factories for the billing domain."""

import factory
from factory.django import DjangoModelFactory

from apps.billing.models import ServiceProvider


class ServiceProviderFactory(DjangoModelFactory):
    """A GePG service provider."""

    class Meta:
        model = ServiceProvider
        django_get_or_create = ("sp_code",)

    sp_code = factory.Sequence(lambda n: f"SP{n:04d}")
    name = factory.Sequence(lambda n: f"Service Provider {n}")
    group_code = "TGC"
    sys_code = "TGCSYS"
    is_active = True
