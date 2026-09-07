"""Serializers for the product domain."""

from rest_framework import serializers

from apps.core.serializers import AuditFieldsMixin

from .models import (
    Brand,
    Product,
    ProductCategory,
    ProductImage,
    ProductStatus,
    Tag,
    UnitOfMeasure,
)


class ReferenceSerializer(AuditFieldsMixin):
    """Shared shape for the catalog's lookup tables."""

    class Meta:
        fields = (
            "id",
            "name",
            "description",
            "is_active",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = AuditFieldsMixin.AUDIT_FIELDS


class ProductCategorySerializer(ReferenceSerializer):
    """Product categories, including their parent link."""

    class Meta(ReferenceSerializer.Meta):
        model = ProductCategory
        fields = (*ReferenceSerializer.Meta.fields, "slug", "parent")
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "slug")


class BrandSerializer(ReferenceSerializer):
    """Brands."""

    class Meta(ReferenceSerializer.Meta):
        model = Brand
        fields = (*ReferenceSerializer.Meta.fields, "slug", "website_url", "country")
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "slug")


class ProductStatusSerializer(ReferenceSerializer):
    """Product publication states."""

    class Meta(ReferenceSerializer.Meta):
        model = ProductStatus
        fields = (*ReferenceSerializer.Meta.fields, "color")


class UnitOfMeasureSerializer(ReferenceSerializer):
    """Units of measure."""

    class Meta(ReferenceSerializer.Meta):
        model = UnitOfMeasure
        fields = (*ReferenceSerializer.Meta.fields, "code")


class TagSerializer(ReferenceSerializer):
    """Tags."""

    class Meta(ReferenceSerializer.Meta):
        model = Tag
        fields = (*ReferenceSerializer.Meta.fields, "slug", "color")
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "slug")


class ProductImageSerializer(AuditFieldsMixin):
    """An image attached to a product."""

    class Meta:
        model = ProductImage
        fields = (
            "id",
            "product",
            "image",
            "alt_text",
            "sort_order",
            "is_primary",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "is_primary")


class ProductSerializer(AuditFieldsMixin):
    """Full product representation.

    Related lookups are exposed twice: a writable id field, and a read-only
    nested ``*_detail`` object. That keeps writes simple while sparing clients a
    second round trip just to render a category name.
    """

    product_category_detail = ProductCategorySerializer(
        source="product_category", read_only=True
    )
    brand_detail = BrandSerializer(source="brand", read_only=True)
    product_status_detail = ProductStatusSerializer(
        source="product_status", read_only=True
    )
    unit_of_measure_detail = UnitOfMeasureSerializer(
        source="unit_of_measure", read_only=True
    )
    tags_detail = TagSerializer(source="tags", many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "barcode",
            "short_description",
            "description",
            "product_category",
            "product_category_detail",
            "brand",
            "brand_detail",
            "product_status",
            "product_status_detail",
            "unit_of_measure",
            "unit_of_measure_detail",
            "tags",
            "tags_detail",
            "images",
            "price",
            "cost_price",
            "discount_percentage",
            "tax_rate",
            "currency",
            "stock_quantity",
            "reorder_level",
            "weight",
            "length",
            "width",
            "height",
            "warranty_months",
            "rating",
            "is_active",
            "is_featured",
            "is_digital",
            "requires_shipping",
            "released_at",
            "available_from",
            "expiry_date",
            "specifications",
            "metadata",
            "color",
            "website_url",
            "contact_email",
            "image",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "slug")

    def validate(self, attrs):
        """Reject an expiry that precedes the release date."""
        released_at = attrs.get("released_at") or getattr(
            self.instance, "released_at", None
        )
        expiry_date = attrs.get("expiry_date") or getattr(
            self.instance, "expiry_date", None
        )
        if released_at and expiry_date and expiry_date < released_at:
            raise serializers.ValidationError(
                {"expiry_date": "Expiry date cannot precede the release date."}
            )
        return attrs
