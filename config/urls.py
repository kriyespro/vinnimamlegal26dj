from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", include("apps.console.urls")),  # custom owner console
    path(f"{settings.ADMIN_URL}/", admin.site.urls),  # Django admin (advanced) — /sd/
    path("", include("apps.leads.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.portal.urls")),
    path("", include("apps.billing.urls")),
    path("", include("apps.core.urls")),
]

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
