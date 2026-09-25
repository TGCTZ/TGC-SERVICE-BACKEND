"""API views for authentication, users, roles and permissions."""

import contextlib

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
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
    FirstLoginPasswordSerializer,
    FirstLoginProfileSerializer,
    GenderSerializer,
    IdentityDetailSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    PermissionSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserStatusSerializer,
)
from .services.accounts import (
    complete_first_login_password,
    complete_first_login_profile,
    create_user_account,
    reset_temporary_password,
)
from .services.auth import change_password, record_login
from .services.roles import (
    assert_can_assign,
    assert_can_create_role,
    assert_can_grant,
    assert_can_manage_role,
    assert_can_manage_user,
    hidden_role_names,
    permission_labels,
)

User = get_user_model()


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


class FirstLoginPasswordView(APIView):
    """First login, step one: replace the temporary password with the user's own."""

    serializer_class = FirstLoginPasswordSerializer
    throttle_scope = "auth"

    @extend_schema(request=FirstLoginPasswordSerializer, responses={200: dict})
    def post(self, request):
        """Set the password; answer with a fresh token pair and the user."""
        serializer = FirstLoginPasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        tokens = complete_first_login_password(
            user=request.user, password=serializer.validated_data["password"]
        )
        return Response(
            {
                **tokens,
                "user": MeSerializer(request.user, context={"request": request}).data,
            }
        )


class FirstLoginProfileView(APIView):
    """First login, step two: the profile the system needs before anything else."""

    serializer_class = FirstLoginProfileSerializer

    @extend_schema(request=FirstLoginProfileSerializer, responses=MeSerializer)
    def post(self, request):
        """Save the profile and open the app to the user."""
        serializer = FirstLoginProfileSerializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        complete_first_login_profile(user=request.user, serializer=serializer)
        return Response(MeSerializer(request.user, context={"request": request}).data)


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

    # Roles can arrive with a create, an update, or the roles action; all three
    # go through the same rank checks - see services/roles.py.

    def get_queryset(self):
        """Leave out accounts ranked above the requester; fetching one is a 404.

        Superusers count as the top rank, so they vanish along with superadmin.
        """
        queryset = super().get_queryset()
        hidden = hidden_role_names(self.request.user)
        if not hidden:
            return queryset
        return queryset.exclude(groups__name__in=hidden).exclude(is_superuser=True)

    # No self-registration: this is the only way an account is made. Reset
    # issues a password, so it asks for change_user rather than add_user.
    action_permissions = {"reset_password": ["users.change_user"]}

    def get_serializer_class(self):
        """Creating takes only an email and a role; everything else is the full record."""
        if self.action == "create":
            return UserCreateSerializer
        return super().get_serializer_class()

    @extend_schema(request=UserCreateSerializer, responses={201: UserSerializer})
    def create(self, request, *args, **kwargs):
        """Create the account and email its credentials.

        The temporary password is in this response and nowhere else afterwards,
        so whoever created the account can pass it on if the email goes astray.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, password = create_user_account(
            email=serializer.validated_data["email"],
            role=serializer.validated_data["role"],
            actor=request.user,
        )
        data = UserSerializer(user, context=self.get_serializer_context()).data
        return Response(
            {**data, "temporary_password": password}, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses=UserSerializer)
    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """Issue a new temporary password, email it, and show it once."""
        from apps.core.exceptions import ServiceError

        user = self.get_object()
        if user.pk == request.user.pk:
            raise ServiceError("Change your own password from Settings.")
        assert_can_manage_user(request.user, user)
        password = reset_temporary_password(user=user)
        data = self.get_serializer(user).data
        return Response({**data, "temporary_password": password})

    def perform_update(self, serializer):
        """Refuse to edit a superior's account, or to change roles beyond one's rank."""
        user = serializer.instance
        assert_can_manage_user(self.request.user, user)
        groups = serializer.validated_data.get("groups")
        if groups is not None:
            assert_can_assign(
                self.request.user,
                before={group.name for group in user.groups.all()},
                after={group.name for group in groups},
            )
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        """Refuse to delete an account ranked at or above the requester."""
        assert_can_manage_user(self.request.user, instance)
        super().perform_destroy(instance)

    @extend_schema(request=RoleSerializer, responses=UserSerializer)
    @action(detail=True, methods=["put"], url_path="roles")
    def set_roles(self, request, pk=None):
        """Replace this user's roles with the supplied list of names."""
        from .services.roles import sync_user_roles

        user = self.get_object()
        assert_can_manage_user(request.user, user)
        sync_user_roles(
            user=user, role_names=request.data.get("roles", []), actor=request.user
        )
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

    def get_permissions(self):
        """Anyone signed in may read the options; changing them stays gated.

        Every user's own profile offers a gender - the first-login step
        requires one - whatever their role's model permissions say.
        """
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return super().get_permissions()


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

    queryset = Group.objects.prefetch_related("permissions__content_type").order_by(
        "name"
    )
    serializer_class = RoleSerializer
    permission_classes = [StrictModelPermissions]
    search_fields = ("name",)
    ordering_fields = ("id", "name")

    def get_queryset(self):
        """Leave out roles ranked above the requester; fetching one by id is a 404."""
        return (
            super().get_queryset().exclude(name__in=hidden_role_names(self.request.user))
        )

    def perform_create(self, serializer):
        """Create a role below the requester, holding only what they can grant."""
        assert_can_create_role(self.request.user, serializer.validated_data["name"])
        assert_can_grant(
            self.request.user,
            before=set(),
            after=permission_labels(serializer.validated_data.get("permissions", [])),
        )
        serializer.save()

    def perform_update(self, serializer):
        """Block changes to protected roles, and to roles at or above the requester."""
        role = serializer.instance
        assert_can_manage_role(
            self.request.user, role, new_name=serializer.validated_data.get("name")
        )
        if "permissions" in serializer.validated_data:
            assert_can_grant(
                self.request.user,
                before=permission_labels(role.permissions.all()),
                after=permission_labels(serializer.validated_data["permissions"]),
            )
        serializer.save()

    def perform_destroy(self, instance):
        """Block deletion of protected roles, and of roles at or above the requester."""
        assert_can_manage_role(self.request.user, instance)
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
        """Permissions bucketed by app label, for rendering a role editor.

        Values are full ``app_label.codename`` labels rather than bare
        codenames, so they are the same strings a role's own ``permissions``
        array holds and the editor can write back exactly what it read. A bare
        codename would also be ambiguous - see ``PermissionLabelField``.
        """
        buckets: dict[str, list[str]] = {}
        for permission in self.filter_queryset(self.get_queryset()):
            app_label = permission.content_type.app_label
            buckets.setdefault(app_label, []).append(f"{app_label}.{permission.codename}")
        return Response(buckets)
