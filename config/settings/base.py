"""Shared settings for every environment.

Environment-specific modules import ``*`` from here and override what differs.
Deployment-varying values come from the environment via django-environ, never
from hardcoded defaults - see ``.env.example``.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

# No default: a missing SECRET_KEY must crash loudly rather than silently
# falling back to a shared, guessable value.
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Applications
#
# Local apps are listed in dependency-layer order. Imports point downward only:
# an app may import from a lower layer, never from the same layer or a higher
# one. Data shared by two apps in the same layer belongs one layer down.
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "auditlog",
]

LOCAL_APPS = [
    "apps.core",  # L1 - base models, managers, shared DRF machinery
    "apps.users",  # L2 - custom user, authentication, RBAC
    "apps.audit",  # L2 - activity-log and system-log read APIs
    "apps.catalog",  # L3 - product domain
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # As early as possible: it must be able to answer a preflight OPTIONS
    # request before CommonMiddleware redirects or otherwise rewrites it.
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # DRF authenticates inside the view, which is too late for the two
    # middlewares below. This resolves the bearer token up front so both of
    # them see the real user instead of AnonymousUser.
    "apps.core.middleware.APIAuthenticationMiddleware",
    # Must follow the two above: it reads request.user.
    "apps.core.current_user.CurrentUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
# Every request runs in a transaction: a view that raises leaves no partial write.
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# Browser clients on another origin. Empty by default, so a misconfigured
# deployment blocks requests rather than accepting them from anywhere.
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
# The JWT travels in the Authorization header, not a cookie, so the browser
# never needs to send credentials cross-origin.
CORS_ALLOW_CREDENTIALS = False

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Deny by default. Every view declares its own permissions explicitly, so
    # forgetting to do so fails closed rather than open.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 15,
    "DEFAULT_FILTER_BACKENDS": ["apps.core.filters.WhitelistFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.handlers.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        # Tight by design: these are the endpoints worth brute-forcing.
        "auth": "6/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    # The auth service stamps last_login_at instead, in one place.
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Django API Template",
    "DESCRIPTION": "Reusable Django REST API starter.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
}

# Models are registered explicitly in apps.core.audit by walking BaseModel
# subclasses, so auditlog must not blanket-register everything itself.
AUDITLOG_INCLUDE_ALL_MODELS = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        # apps.audit parses this exact format back out for the system-log API.
        "standard": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "app.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": env("LOG_LEVEL", default="INFO"),
    },
}
