"""JWT authentication that holds new accounts to their first login.

An account created from the Users screen must set its own password and then
complete its profile before it can do anything else. The frontend walks the
user through that, but the rule lives here, on every request: a UI redirect
alone can be bypassed with a token and curl.
"""

from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

#: What a user may reach before finishing their first login, by URL name - and
#: for which methods (None means any). Enough to sign in and out, read who they
#: are, do the two first-login steps, and fill the profile step's gender list.
FIRST_LOGIN_ALLOWED = {
    "auth-login": None,
    "auth-refresh": None,
    "auth-logout": None,
    "auth-me": {"GET", "HEAD", "OPTIONS"},
    "auth-first-login-password": None,
    "auth-first-login-profile": None,
    "config": None,
    "gender-list": {"GET", "HEAD", "OPTIONS"},
}


class FirstLoginRequired(PermissionDenied):
    """403 whose body carries a ``code`` the frontend recognises and redirects on.

    DRF writes only ``detail`` into the body; the code is put there explicitly
    so the client does not have to match on wording.
    """

    CODE = "first_login_required"
    MESSAGE = "Finish setting up your account before using the system."

    def __init__(self):
        """Always the same body: the message and the code."""
        super().__init__({"detail": self.MESSAGE, "code": self.CODE})


class OnboardingJWTAuthentication(JWTAuthentication):
    """Simple JWT, plus: refuse all but the first-login steps until they are done."""

    def authenticate(self, request):
        """Authenticate as usual, then check the first-login flags."""
        result = super().authenticate(request)
        if result is None:
            return None

        user, _ = result
        if user.must_change_password or user.must_complete_profile:
            match = getattr(request._request, "resolver_match", None)
            methods = FIRST_LOGIN_ALLOWED.get(getattr(match, "url_name", None), False)
            if methods is False or (
                methods is not None and request.method not in methods
            ):
                raise FirstLoginRequired()
        return result
