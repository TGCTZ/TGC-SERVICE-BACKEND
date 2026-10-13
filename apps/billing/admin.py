"""Read-only staff views for durable GePG messages and retry state."""

from django.contrib import admin

from .models import GePGCallback, GePGRequest


@admin.register(GePGCallback)
class GePGCallbackAdmin(admin.ModelAdmin):
    """Expose callback queue health and failures without editing raw messages."""

    list_display = ("kind", "event_id", "status", "attempts", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("event_id", "last_error")
    readonly_fields = tuple(field.name for field in GePGCallback._meta.fields)

    def has_add_permission(self, request):
        """Keep inbox events immutable from the admin UI."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent staff from editing signed callback evidence."""
        return False

    def has_view_permission(self, request, obj=None):
        """Limit callback payload visibility to staff users."""
        return request.user.is_staff


@admin.register(GePGRequest)
class GePGRequestAdmin(admin.ModelAdmin):
    """Show outbound request retries and terminal failures to staff."""

    list_display = (
        "operation",
        "req_id",
        "status",
        "attempts",
        "next_attempt_at",
        "updated_at",
    )
    list_filter = ("operation", "status")
    search_fields = ("req_id", "last_error", "status_desc")
    readonly_fields = tuple(field.name for field in GePGRequest._meta.fields)

    def has_add_permission(self, request):
        """Keep outbound request evidence immutable from the admin UI."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent staff from editing persisted outbound requests."""
        return False

    def has_view_permission(self, request, obj=None):
        """Limit request payload visibility to staff users."""
        return request.user.is_staff
