"""Test settings - optimised for speed, not realism."""

from .base import *

DEBUG = False

# Tests use the offline GePG path; live signing stays covered by generated-key tests.
GEPG_USE_DIGITAL_SIGNATURE = False
GEPG_SIMULATE = True

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

# Callback tasks run inline in tests; no Redis service is needed for the suite.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
