"""Production settings - secure defaults, no debug affordances."""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
]

if GEPG_SIMULATE:
    raise ImproperlyConfigured("GEPG_SIMULATE must be disabled in production.")

if not GEPG_SIMULATE:
    required_gepg_settings = {
        "GEPG_USE_DIGITAL_SIGNATURE": GEPG_USE_DIGITAL_SIGNATURE,
        "GEPG_COM": GEPG_COM,
        "GEPG_ALG": GEPG_ALG,
        "GEPG_PRIVATE_KEY_PATH": Path(GEPG_PRIVATE_KEY_PATH).is_file(),
        "GEPG_PUBLIC_CERT_PATH": Path(GEPG_PUBLIC_CERT_PATH).is_file(),
    }
    missing_gepg_settings = [
        name for name, configured in required_gepg_settings.items() if not configured
    ]
    if missing_gepg_settings:
        raise ImproperlyConfigured(
            "Production GePG integration is not ready; configure: "
            + ", ".join(missing_gepg_settings)
        )
