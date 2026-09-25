"""Serializers for the notification inbox."""

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """A notification as its recipient sees it. Read-only: the API only marks."""

    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "title",
            "body",
            "link",
            "created_at",
            "read_at",
            "is_read",
        )
        read_only_fields = fields
