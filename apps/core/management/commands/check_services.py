"""Pre-flight / ops health report: `python manage.py check_services` (exit code 1 if anything critical fails)."""
import os
import sys
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Check database, cache/Redis, static build, secrets, email, Razorpay and media storage."

    def handle(self, *args, **options):
        problems, warnings = [], []

        def ok(msg):
            self.stdout.write(self.style.SUCCESS(f"  ok    {msg}"))

        def warn(msg):
            warnings.append(msg)
            self.stdout.write(self.style.WARNING(f"  warn  {msg}"))

        def fail(msg):
            problems.append(msg)
            self.stdout.write(self.style.ERROR(f"  FAIL  {msg}"))

        engine = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
        try:
            with connection.cursor() as c:
                c.execute("SELECT 1")
            ok(f"database reachable ({engine})")
            if engine == "sqlite3" and not settings.DEBUG:
                warn("SQLite in production — use PostgreSQL")
        except Exception as exc:
            fail(f"database: {exc}")

        backend = settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]
        try:
            cache.set("svc-check", "1", 5)
            assert cache.get("svc-check") == "1", "value did not round-trip (backend unreachable?)"
            ok(f"cache works ({backend})")
        except Exception as exc:
            fail(f"cache ({backend}): {exc}")
        if settings.REDIS_URL:
            try:
                import redis

                redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2).ping()
                ok("Redis ping")
            except Exception as exc:
                fail(f"Redis unreachable: {exc}")
        elif not settings.DEBUG:
            warn("REDIS_URL not set — rate limits/sessions use the DB cache (works, but Redis is faster)")
        if backend == "LocMemCache" and not settings.DEBUG:
            fail("per-process memory cache in production: rate limits are not shared between workers")

        if not settings.DEBUG:
            if len(settings.SECRET_KEY) < 50 or settings.SECRET_KEY.startswith("dev-"):
                fail("SECRET_KEY is short or a dev key")
            else:
                ok("SECRET_KEY length ok")
            if not settings.ALLOWED_HOSTS:
                fail("ALLOWED_HOSTS empty")
        css = Path(settings.BASE_DIR) / "static" / "css" / "app.min.css"
        ok(f"CSS built ({css.stat().st_size // 1024} KB)") if css.exists() else fail("static/css/app.min.css missing — run `npm run build:css`")
        if not settings.DEBUG and not (Path(settings.STATIC_ROOT) / "staticfiles.json").exists():
            fail("collectstatic has not been run (no staticfiles.json)")
        media = Path(settings.PRIVATE_MEDIA_ROOT)
        try:
            media.mkdir(parents=True, exist_ok=True)
            probe = media / ".probe"
            probe.write_text("x")
            probe.unlink()
            ok(f"private media writable ({media})")
        except Exception as exc:
            fail(f"private media not writable: {exc}")
        if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST:
            warn("SMTP EMAIL_HOST not set — password-reset emails cannot be sent")
        else:
            ok(f"email backend {settings.EMAIL_BACKEND.rsplit('.', 2)[-2]}")
        if settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and settings.RAZORPAY_WEBHOOK_SECRET:
            ok("Razorpay keys + webhook secret configured" + (" (TEST mode)" if settings.RAZORPAY_KEY_ID.startswith("rzp_test_") else " (LIVE)"))
        else:
            warn("Razorpay not fully configured — online payments disabled")
        if settings.SITE_EMAIL.endswith("example.com") or "00000" in settings.SITE_PHONE:
            warn("SITE_EMAIL / SITE_PHONE are still placeholders")
        self.stdout.write(f"\n{len(problems)} problem(s), {len(warnings)} warning(s)")
        if problems:
            sys.exit(1)
