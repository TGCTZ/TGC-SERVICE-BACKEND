"""API views for the product domain."""

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet

from .models import (
    Brand,
    Product,
    ProductCategory,
    ProductImage,
    ProductStatus,
    Tag,
    UnitOfMeasure,
)
from .serializers import (
    BrandSerializer,
    ProductCategorySerializer,
    ProductImageSerializer,
    ProductSerializer,
    ProductStatusSerializer,
    TagSerializer,
    UnitOfMeasureSerializer,
)
from .services.product import set_primary_image


class ProductViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over products."""

    # select_related for the to-one links and prefetch_related for the to-many
    # ones: without these, serialising a page of 15 products issues dozens of
    # queries instead of a handful.
    queryset = Product.objects.select_related(
        "product_category", "brand", "product_status", "unit_of_measure"
    ).prefetch_related("tags", "images")
    serializer_class = ProductSerializer

    search_fields = ("name", "sku", "barcode", "short_description", "description")
    filter_fields = (
        "product_category",
        "brand",
        "product_status",
        "unit_of_measure",
        "is_active",
        "is_featured",
        "is_digital",
        "requires_shipping",
        "currency",
    )
    ordering_fields = (
        "id",
        "name",
        "sku",
        "price",
        "stock_quantity",
        "rating",
        "is_featured",
        "released_at",
        "created_at",
    )
    date_filter_fields = ("created_at", "updated_at", "released_at", "expiry_date")

    @extend_schema(request=ProductImageSerializer, responses=ProductImageSerializer)
    @action(detail=True, methods=["post"], url_path="images")
    def upload_image(self, request, pk=None):
        """Attach an image to this product."""
        product = self.get_object()
        # QueryDict is immutable on a multipart request, so copy before injecting
        # the product id the client should not have to repeat in the body.
        payload = request.data.copy()
        payload["product"] = product.pk
        serializer = ProductImageSerializer(
            data=payload, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductImageViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over product images."""

    queryset = ProductImage.objects.select_related("product")
    serializer_class = ProductImageSerializer
    filter_fields = ("product", "is_primary")
    ordering_fields = ("id", "sort_order", "created_at")

    @extend_schema(request=None, responses=ProductImageSerializer)
    @action(detail=True, methods=["patch"])
    def primary(self, request, pk=None):
        """Promote this image to be its product's primary one."""
        image = set_primary_image(image=self.get_object())
        return Response(self.get_serializer(image).data)


class ProductCategoryViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over product categories."""

    queryset = ProductCategory.objects.select_related("parent")
    serializer_class = ProductCategorySerializer
    search_fields = ("name", "description", "slug")
    filter_fields = ("is_active", "parent")
    ordering_fields = ("id", "name", "is_active", "created_at")


class BrandViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over brands."""

    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    search_fields = ("name", "description", "country")
    filter_fields = ("is_active", "country")
    ordering_fields = ("id", "name", "is_active", "created_at")


class ProductStatusViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over product statuses."""

    queryset = ProductStatus.objects.all()
    serializer_class = ProductStatusSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")


class UnitOfMeasureViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over units of measure."""

    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    search_fields = ("name", "description", "code")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "code", "created_at")


class TagViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over tags."""

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    search_fields = ("name", "description", "slug")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")
