"""OpenAPI support for the users app's custom authentication."""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class OnboardingJWTScheme(SimpleJWTScheme):
    """Describe onboarding authentication using the standard JWT bearer scheme."""

    target_class = "apps.users.authentication.OnboardingJWTAuthentication"
    priority = 0
