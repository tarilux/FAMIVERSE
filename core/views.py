from django.http import JsonResponse
from django.shortcuts import render
from django.db import connection
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    connection.ensure_connection()
    return JsonResponse({"status": "ok"})


@require_GET
@never_cache
def pwa_manifest(request):
    return render(
        request,
        "pwa/manifest.webmanifest",
        content_type="application/manifest+json",
    )


@require_GET
@never_cache
def service_worker(request):
    response = render(
        request,
        "pwa/service-worker.js",
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    return response


@require_GET
def offline_page(request):
    return render(request, "pwa/offline.html")
