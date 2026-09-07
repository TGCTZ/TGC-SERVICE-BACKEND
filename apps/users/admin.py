"""Django admin registration for the users app."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Gender, IdentityDetail, UserStatus

User = get_user_model()


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom user model, keyed on email rather than username."""

    ordering = ["-id"]
    list_display = ("email", "username", "full_name", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "username", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        (
            "Personal",
            {
                "fields": (
                    "first_name",
                    "middle_name",
                    "last_name",
                    "date_of_birth",
                    "gender",
                    "bio",
                    "avatar",
                )
            },
        ),
        (
            "Contact",
            {
                "fields": (
                    "phone_number",
                    "address_line1",
                    "address_line2",
                    "city",
                    "state",
                    "postal_code",
                    "country",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "user_status",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "last_login_at", "deleted_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        """Show soft-deleted users too - the admin is where they get recovered."""
        return User.all_objects.all()


admin.site.register([UserStatus, Gender, IdentityDetail])
