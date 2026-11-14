from django.contrib import admin
from django.urls import include, path
from django.views.i18n import set_language

from accounts.views import home
from core.views import health_check, offline_page, pwa_manifest, service_worker

urlpatterns = [
    path("", home, name="root"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("missions/", include("missions.urls")),
    path("habits/", include("habits.urls")),
    path("progression/", include("progression.urls")),
    path("rewards/", include("rewards.urls")),
    path("communications/", include("communications.urls")),
    path("printing/", include("printcenter.urls")),
    path("backups/", include("backupcenter.urls")),
    path("healthz/", health_check, name="health_check"),
    path("manifest.webmanifest", pwa_manifest, name="pwa_manifest"),
    path("service-worker.js", service_worker, name="service_worker"),
    path("offline/", offline_page, name="offline"),
    path("i18n/setlang/", set_language, name="set_language"),
]
