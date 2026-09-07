"""Service layer for the catalog app."""

from .product import set_primary_image, sync_tags

__all__ = ["set_primary_image", "sync_tags"]
