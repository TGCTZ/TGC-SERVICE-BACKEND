"""Product domain models.

The five lookup tables inherit ``ReferenceModel``, so they share a name,
description, active flag, soft delete and the partial unique constraint that
lets a deleted name be reused.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from apps.core.models import BaseModel, ReferenceModel


class ProductCategory(ReferenceModel):
    """Hierarchical grouping of products."""

    slug = models.SlugField(max_length=140)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )

    class Meta(ReferenceModel.Meta):
        verbose_name_plural = "product categories"
        constraints = [
            *ReferenceModel.Meta.constraints,
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_slug",
            ),
        ]

    def save(self, *args, **kwargs):
        """Derive the slug from the name when one is not supplied."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Brand(ReferenceModel):
    """Manufacturer or marque a product belongs to."""

    slug = models.SlugField(max_length=140)
    website_url = models.URLField(blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta(ReferenceModel.Meta):
        constraints = [
            *ReferenceModel.Meta.constraints,
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_slug",
            ),
        ]

    def save(self, *args, **kwargs):
        """Derive the slug from the name when one is not supplied."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductStatus(ReferenceModel):
    """Publication state, e.g. Draft, Published, Discontinued."""

    color = models.CharField(max_length=20, blank=True)

    class Meta(ReferenceModel.Meta):
        verbose_name_plural = "product statuses"


class UnitOfMeasure(ReferenceModel):
    """Unit a product is sold in, e.g. piece, kilogram, litre."""

    code = models.CharField(max_length=20)

    class Meta(ReferenceModel.Meta):
        constraints = [
            *ReferenceModel.Meta.constraints,
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_code",
            ),
        ]


class Tag(ReferenceModel):
    """Free-form label applied to products."""

    slug = models.SlugField(max_length=140)
    color = models.CharField(max_length=20, blank=True)

    class Meta(ReferenceModel.Meta):
        constraints = [
            *ReferenceModel.Meta.constraints,
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_slug",
            ),
        ]

    def save(self, *args, **kwargs):
        """Derive the slug from the name when one is not supplied."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(BaseModel):
    """A sellable item."""

    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=280)
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=100, blank=True)
    short_description = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)

    product_category = models.ForeignKey(
        ProductCategory, on_delete=models.PROTECT, related_name="products"
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    product_status = models.ForeignKey(
        ProductStatus, on_delete=models.PROTECT, related_name="products"
    )
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    tags = models.ManyToManyField(Tag, through="ProductTag", related_name="products")

    # Decimal, never float: money must not accumulate binary rounding error.
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    currency = models.CharField(max_length=3, default="USD")

    stock_quantity = models.IntegerField(default=0, db_index=True)
    reorder_level = models.IntegerField(null=True, blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    warranty_months = models.IntegerField(null=True, blank=True)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )

    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_digital = models.BooleanField(default=False)
    requires_shipping = models.BooleanField(default=True)

    released_at = models.DateField(null=True, blank=True)
    available_from = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    specifications = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    color = models.CharField(max_length=50, blank=True)
    website_url = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True)
    image = models.ImageField(upload_to="products/", null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["price"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            # Partial: a soft-deleted product must not hold its SKU or slug
            # hostage against a future one.
            models.UniqueConstraint(
                fields=["sku"],
                condition=Q(deleted_at__isnull=True),
                name="catalog_product_unique_sku",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(deleted_at__isnull=True),
                name="catalog_product_unique_slug",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        """Derive the slug from the name when one is not supplied."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductTag(BaseModel):
    """Through model for the product/tag relationship.

    An explicit through model rather than a plain ManyToMany so the link itself
    carries audit columns - who tagged what, and when.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "tag"], name="catalog_producttag_unique"
            )
        ]


class ProductImage(BaseModel):
    """An image belonging to a product."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["product", "sort_order"])]

    def __str__(self) -> str:
        return f"{self.product.name} image {self.pk}"
