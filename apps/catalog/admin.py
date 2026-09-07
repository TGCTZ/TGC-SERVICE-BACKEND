"""Django admin registration for the catalog app."""

from django.contrib import admin

from .models import (
    Brand,
    Product,
    ProductCategory,
    ProductImage,
    ProductStatus,
    Tag,
    UnitOfMeasure,
)


class ProductImageInline(admin.TabularInline):
    """Edit a product's images alongside the product itself."""

    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin for products."""

    list_display = ("name", "sku", "price", "stock_quantity", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "product_category", "brand")
    search_fields = ("name", "sku", "barcode")
    inlines = [ProductImageInline]


admin.site.register([ProductCategory, Brand, ProductStatus, UnitOfMeasure, Tag])
