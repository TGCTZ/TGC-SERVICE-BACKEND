"""Test settings - optimised for speed, not realism."""

from .base import *

DEBUG = False

# SQLite in memory: the suite needs no external database service.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# Orders of magnitude faster than the default hasher, and the suite creates
# a great many users.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Throttling would make auth tests order-dependent and flaky.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"auth": None}

LOGGING["root"]["handlers"] = ["console"]
