"""Business operations on products."""

from django.db import transaction

from apps.catalog.models import ProductImage, Tag
from apps.core.exceptions import ServiceError


@transaction.atomic
def sync_tags(*, product, tag_ids: list[int]):
    """Replace a product's tags with ``tag_ids``.

    Raises:
        ServiceError: If any id does not match a live tag.
    """
    tags = list(Tag.objects.filter(pk__in=tag_ids))
    missing = set(tag_ids) - {tag.pk for tag in tags}
    if missing:
        raise ServiceError(f"Unknown tag id(s): {sorted(missing)}")
    product.tags.set(tags)
    return product


@transaction.atomic
def set_primary_image(*, image: ProductImage) -> ProductImage:
    """Make ``image`` the product's primary one, demoting any previous holder.

    The demotion and promotion happen in one transaction because a product with
    two primary images renders unpredictably, and one with none renders blank.
    """
    ProductImage.objects.filter(product=image.product, is_primary=True).exclude(
        pk=image.pk
    ).update(is_primary=False)
    image.is_primary = True
    image.save(update_fields=["is_primary", "updated_at"])
    return image
