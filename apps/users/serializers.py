"""Serializers for users, roles and authentication."""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password

from apps.core.serializers import AuditFieldsMixin

from .models import Gender, IdentityDetail, UserStatus

User = get_user_model()


class ReferenceSerializer(AuditFieldsMixin):
    """Base serializer for lookup tables built on ``ReferenceModel``."""

    class Meta:
        fields = (
            "id",
            "name",
            "description",
            "is_active",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = AuditFieldsMixin.AUDIT_FIELDS


class UserStatusSerializer(ReferenceSerializer):
    """Account lifecycle states."""

    class Meta(ReferenceSerializer.Meta):
        model = UserStatus


class GenderSerializer(ReferenceSerializer):
    """Gender options."""

    class Meta(ReferenceSerializer.Meta):
        model = Gender


class PermissionSerializer(serializers.ModelSerializer):
    """A single Django permission, presented by its full label."""

    label = serializers.SerializerMethodField()
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)

    class Meta:
        model = Permission
        fields = ("id", "name", "codename", "app_label", "label")

    def get_label(self, obj) -> str:
        """The ``app_label.codename`` string used throughout the role matrix."""
        return f"{obj.content_type.app_label}.{obj.codename}"


class RoleSerializer(serializers.ModelSerializer):
    """A role, exposed as a group plus its permission labels."""

    permissions = serializers.SlugRelatedField(
        many=True,
        slug_field="codename",
        queryset=Permission.objects.all(),
        required=False,
    )
    is_protected = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ("id", "name", "permissions", "is_protected", "user_count")

    def get_is_protected(self, obj) -> bool:
        """True when the API refuses to rename, delete or re-scope this role."""
        from apps.users.roles import PROTECTED_ROLES

        return obj.name in PROTECTED_ROLES

    def get_user_count(self, obj) -> int:
        """How many users hold this role."""
        return obj.user_set.count()


class UserSerializer(AuditFieldsMixin):
    """Full user representation used by the ``/users/`` endpoints."""

    full_name = serializers.CharField(read_only=True)
    roles = serializers.SlugRelatedField(
        source="groups",
        many=True,
        slug_field="name",
        queryset=Group.objects.all(),
        required=False,
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, validators=[validate_password]
    )
    gender_detail = GenderSerializer(source="gender", read_only=True)
    user_status_detail = UserStatusSerializer(source="user_status", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "username",
            "email",
            "password",
            "phone_number",
            "emergency_contact_name",
            "emergency_contact_number",
            "date_of_birth",
            "gender",
            "gender_detail",
            "user_status",
            "user_status_detail",
            "bio",
            "avatar",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "timezone",
            "locale",
            "is_active",
            "is_staff",
            "last_login_at",
            "email_verified_at",
            "roles",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = (
            "last_login_at",
            "email_verified_at",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )

    def create(self, validated_data):
        """Create a user, hashing the password rather than storing it raw."""
        groups = validated_data.pop("groups", None)
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        if groups is not None:
            user.groups.set(groups)
        return user

    def update(self, instance, validated_data):
        """Update a user; a blank password means 'leave it unchanged'."""
        groups = validated_data.pop("groups", None)
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        if groups is not None:
            instance.groups.set(groups)
        return instance


class MeSerializer(UserSerializer):
    """The authenticated user's own record, plus their effective permissions."""

    permissions = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = (*UserSerializer.Meta.fields, "permissions")
        read_only_fields = (
            *UserSerializer.Meta.read_only_fields,
            "is_active",
            "is_staff",
            "roles",
        )

    def get_permissions(self, obj) -> list[str]:
        """Flat list of permission labels, for driving UI visibility."""
        return sorted(obj.get_all_permissions())


class IdentityDetailSerializer(AuditFieldsMixin):
    """Identity document attached to a user."""

    class Meta:
        model = IdentityDetail
        fields = (
            "id",
            "user",
            "id_type",
            "id_number",
            "id_document",
            "issue_country",
            "issue_date",
            "expiry_date",
            "verified_at",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = AuditFieldsMixin.AUDIT_FIELDS


class RegisterSerializer(serializers.ModelSerializer):
    """Public self-registration payload."""

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "first_name",
            "middle_name",
            "last_name",
            "username",
            "email",
            "phone_number",
            "password",
            "password_confirm",
        )

    def validate(self, attrs):
        """Reject a mismatched confirmation before anything is written."""
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields do not match."}
            )
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """Payload for an authenticated password change."""

    current_password = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Reject a mismatched confirmation."""
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields do not match."}
            )
        return attrs


class LoginSerializer(TokenObtainPairSerializer):
    """Issues a token pair and returns the authenticated user alongside it.

    Returning the user in the login response saves the client an immediate
    follow-up call to ``/auth/me/`` just to render a name and a permission set.
    """

    @classmethod
    def get_token(cls, user):
        """Embed a couple of cheap claims for clients that decode the token."""
        token = super().get_token(user)
        token["email"] = user.email
        token["full_name"] = user.full_name
        return token

    def validate(self, attrs):
        """Authenticate, then attach the serialised user to the response."""
        data = super().validate(attrs)
        data["user"] = MeSerializer(self.user, context=self.context).data
        return data


class LogoutSerializer(serializers.Serializer):
    """Payload naming the refresh token to blacklist."""

    refresh = serializers.CharField()
