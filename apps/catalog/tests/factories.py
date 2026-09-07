"""Factories for the product domain."""

import factory
from factory.django import DjangoModelFactory

from apps.catalog.models import (
    Brand,
    Product,
    ProductCategory,
    ProductImage,
    ProductStatus,
    Tag,
    UnitOfMeasure,
)


class ProductCategoryFactory(DjangoModelFactory):
    """Product category."""

    class Meta:
        model = ProductCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category {n}")


class BrandFactory(DjangoModelFactory):
    """Brand."""

    class Meta:
        model = Brand
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Brand {n}")
    country = factory.Faker("country")


class ProductStatusFactory(DjangoModelFactory):
    """Product publication state."""

    class Meta:
        model = ProductStatus
        django_get_or_create = ("name",)

    name = factory.Iterator(["Draft", "Published", "Discontinued"])
    color = factory.Iterator(["gray", "green", "red"])


class UnitOfMeasureFactory(DjangoModelFactory):
    """Unit of measure."""

    class Meta:
        model = UnitOfMeasure
        django_get_or_create = ("code",)

    name = factory.Iterator(["Piece", "Kilogram", "Litre", "Metre"])
    code = factory.Iterator(["pc", "kg", "L", "m"])


class TagFactory(DjangoModelFactory):
    """Tag."""

    class Meta:
        model = Tag
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"tag-{n}")


class ProductFactory(DjangoModelFactory):
    """A fully populated product."""

    class Meta:
        model = Product
        django_get_or_create = ("sku",)

    name = factory.Sequence(lambda n: f"Product {n}")
    sku = factory.Sequence(lambda n: f"SKU-{n:05d}")
    barcode = factory.Faker("ean13")
    short_description = factory.Faker("sentence")
    description = factory.Faker("paragraph")
    product_category = factory.SubFactory(ProductCategoryFactory)
    brand = factory.SubFactory(BrandFactory)
    product_status = factory.SubFactory(ProductStatusFactory)
    unit_of_measure = factory.SubFactory(UnitOfMeasureFactory)
    price = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    stock_quantity = factory.Faker("pyint", min_value=0, max_value=500)
    currency = "USD"
    is_active = True


class ProductImageFactory(DjangoModelFactory):
    """Product image row (the file itself is not written)."""

    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = factory.django.ImageField(filename="test.png")
    alt_text = factory.Faker("sentence", nb_words=4)
