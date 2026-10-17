from .base import *  # noqa

import os

if not SECRET_KEY:  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production")

DEBUG = False

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production")
for _name in ("SITE_EMAIL", "SITE_PHONE", "SITE_WHATSAPP"):
    if not os.environ.get(_name):
        raise RuntimeError(f"{_name} must be set in production (real public contact details)")
if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET):  # noqa: F405
    import warnings

    warnings.warn("Razorpay keys are not configured: online payments will be disabled.", stacklevel=2)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
SESSION_COOKIE_AGE = 60 * 60

SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "1") != "0"  # "0" only for local prod-simulation
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]  # load-balancer probes may use plain http
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = os.environ.get("DJANGO_HSTS_PRELOAD", "0") == "1"  # opt-in: hard to undo
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
if not os.environ.get("DATABASE_URL_NAME") and os.environ.get("DJANGO_ALLOW_SQLITE") != "1":
    raise RuntimeError("Production needs PostgreSQL: set DATABASE_URL_NAME (and DATABASE_* vars).")
if os.environ.get("DATABASE_URL_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DATABASE_URL_NAME"],
            "USER": os.environ.get("DATABASE_USER", ""),
            "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
            "HOST": os.environ.get("DATABASE_HOST", "localhost"),
            "PORT": os.environ.get("DATABASE_PORT", "5432"),
        }
    }

if not REDIS_URL:  # noqa: F405
    # No Redis: share rate-limit counters between workers through the database instead of per-process memory.
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "django_cache"}}
    import warnings

    warnings.warn("REDIS_URL not set: using the database cache (run `manage.py createcachetable`). Redis is recommended.", stacklevel=2)
if "default" in DATABASES and DATABASES["default"]["ENGINE"].endswith("postgresql"):  # noqa: F405
    DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
