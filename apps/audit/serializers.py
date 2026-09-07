"""Serializers for audit read APIs."""

from auditlog.models import LogEntry
from rest_framework import serializers


class ActivityLogSerializer(serializers.ModelSerializer):
    """A single change-history entry."""

    action_label = serializers.SerializerMethodField()
    actor_label = serializers.SerializerMethodField()
    subject_type = serializers.CharField(source="content_type.model", read_only=True)

    class Meta:
        model = LogEntry
        fields = (
            "id",
            "action",
            "action_label",
            "subject_type",
            "object_pk",
            "object_repr",
            "changes",
            "actor",
            "actor_label",
            "remote_addr",
            "timestamp",
        )
        read_only_fields = fields

    def get_action_label(self, obj) -> str:
        """Human-readable name of the action, e.g. 'create'."""
        return LogEntry.Action.choices[obj.action][1]

    def get_actor_label(self, obj) -> str:
        """Display name of the acting user, or 'System' when unattributed."""
        return str(obj.actor) if obj.actor_id else "System"


class SystemLogEntrySerializer(serializers.Serializer):
    """One parsed line from the application log file."""

    timestamp = serializers.CharField()
    level = serializers.CharField()
    logger = serializers.CharField()
    message = serializers.CharField()
