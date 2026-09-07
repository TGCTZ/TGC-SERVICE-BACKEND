"""API views for authentication, users, roles and permissions."""

import contextlib

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from apps.core.permissions import StrictModelPermissions
from apps.core.viewsets import BaseModelViewSet

from .models import Gender, IdentityDetail, UserStatus
from .serializers import (
    ChangePasswordSerializer,
    GenderSerializer,
    IdentityDetailSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    PermissionSerializer,
    RegisterSerializer,
    RoleSerializer,
    UserSerializer,
    UserStatusSerializer,
)
from .services.auth import change_password, record_login, register_user
from .services.roles import assert_role_mutable

User = get_user_model()


class RegisterView(CreateAPIView):
    """Public self-registration."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        """Validate the payload, then hand off to the auth service."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(**serializer.validated_data)
        return Response(
            MeSerializer(user, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """Exchange credentials for an access/refresh token pair."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        """Authenticate and stamp the login timestamp on success."""
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            user_id = response.data.get("user", {}).get("id")
            if user_id:
                record_login(User.objects.get(pk=user_id))
        return response


class RefreshView(TokenRefreshView):
    """Exchange a refresh token for a fresh pair."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"


class LogoutView(APIView):
    """Blacklist a refresh token, ending that session."""

    serializer_class = LogoutSerializer

    @extend_schema(request=LogoutSerializer, responses={205: None})
    def post(self, request):
        """Blacklist the supplied refresh token."""
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # An already-expired or already-blacklisted token means the session is
        # already over, which is exactly what the caller asked for.
        with contextlib.suppress(TokenError):
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(RetrieveUpdateAPIView):
    """Read or update the authenticated user's own profile."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """Always the requesting user - there is no id in the URL to tamper with."""
        return self.request.user


class ChangePasswordView(APIView):
    """Change the authenticated user's password."""

    serializer_class = ChangePasswordSerializer
    throttle_scope = "auth"

    @extend_schema(request=ChangePasswordSerializer, responses={204: None})
    def post(self, request):
        """Verify the current password, set the new one, revoke other sessions."""
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over user accounts."""

    queryset = User.objects.select_related("gender", "user_status").prefetch_related(
        "groups"
    )
    serializer_class = UserSerializer

    search_fields = ("first_name", "last_name", "username", "email", "phone_number")
    filter_fields = ("is_active", "is_staff", "user_status", "gender", "city", "country")
    ordering_fields = (
        "id",
        "first_name",
        "last_name",
        "username",
        "email",
        "is_active",
        "last_login_at",
        "created_at",
    )
    date_filter_fields = ("created_at", "updated_at", "last_login_at", "date_of_birth")

    @extend_schema(request=RoleSerializer, responses=UserSerializer)
    @action(detail=True, methods=["put"], url_path="roles")
    def set_roles(self, request, pk=None):
        """Replace this user's roles with the supplied list of names."""
        from .services.roles import sync_user_roles

        user = self.get_object()
        sync_user_roles(user=user, role_names=request.data.get("roles", []))
        return Response(self.get_serializer(user).data)


class UserStatusViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over account lifecycle states."""

    queryset = UserStatus.objects.all()
    serializer_class = UserStatusSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")


class GenderViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over gender options."""

    queryset = Gender.objects.all()
    serializer_class = GenderSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")


class IdentityDetailViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over user identity documents."""

    queryset = IdentityDetail.objects.select_related("user")
    serializer_class = IdentityDetailSerializer
    search_fields = ("id_type", "id_number", "issue_country")
    filter_fields = ("user", "id_type", "issue_country")
    ordering_fields = ("id", "id_type", "expiry_date", "created_at")
    date_filter_fields = ("created_at", "issue_date", "expiry_date", "verified_at")


class RoleViewSet(viewsets.ModelViewSet):
    """CRUD over roles, which are Django groups under the hood."""

    queryset = Group.objects.prefetch_related("permissions").order_by("name")
    serializer_class = RoleSerializer
    permission_classes = [StrictModelPermissions]
    search_fields = ("name",)
    ordering_fields = ("id", "name")

    def perform_update(self, serializer):
        """Block changes to protected roles."""
        assert_role_mutable(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        """Block deletion of protected roles."""
        assert_role_mutable(instance)
        instance.delete()


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only catalogue of every permission the system defines."""

    queryset = Permission.objects.select_related("content_type").order_by(
        "content_type__app_label", "codename"
    )
    serializer_class = PermissionSerializer
    permission_classes = [StrictModelPermissions]
    search_fields = ("name", "codename")
    filter_fields = ("content_type",)
    ordering_fields = ("id", "codename")

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def grouped(self, request):
        """Permissions bucketed by app label, for rendering a role editor."""
        buckets: dict[str, list[str]] = {}
        for permission in self.filter_queryset(self.get_queryset()):
            app_label = permission.content_type.app_label
            buckets.setdefault(app_label, []).append(permission.codename)
        return Response(buckets)
