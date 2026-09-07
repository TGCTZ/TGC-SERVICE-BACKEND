"""URL routes for authentication, users, roles and permissions."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    ChangePasswordView,
    GenderViewSet,
    IdentityDetailViewSet,
    LoginView,
    LogoutView,
    MeView,
    PermissionViewSet,
    RefreshView,
    RegisterView,
    RoleViewSet,
    UserStatusViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("user-statuses", UserStatusViewSet, basename="userstatus")
router.register("genders", GenderViewSet, basename="gender")
router.register("identity-details", IdentityDetailViewSet, basename="identitydetail")
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")

auth_patterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("password/", ChangePasswordView.as_view(), name="auth-password"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("", include(router.urls)),
]
