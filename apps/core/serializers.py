"""Serializer mixins shared across apps."""

from rest_framework import serializers


class AuditFieldsMixin(serializers.ModelSerializer):
    """Expose the read-only audit columns in a consistent shape.

    Actor columns are surfaced as labels rather than raw ids: a client rendering
    a history table wants "Jane Doe", and exposing the id invites an N+1 lookup
    per row.
    """

    created_by_label = serializers.SerializerMethodField()
    updated_by_label = serializers.SerializerMethodField()
    is_deleted = serializers.BooleanField(read_only=True)

    AUDIT_FIELDS = (
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by_label",
        "updated_by_label",
        "is_deleted",
    )

    class Meta:
        abstract = True

    def get_created_by_label(self, obj) -> str | None:
        """Display name of the creating user, if any."""
        return str(obj.created_by) if obj.created_by_id else None

    def get_updated_by_label(self, obj) -> str | None:
        """Display name of the last user to change the row, if any."""
        return str(obj.updated_by) if obj.updated_by_id else None
