from django.urls import path

from . import views

app_name = "backupcenter"

urlpatterns = [
    path("", views.center, name="center"),
    path("settings/", views.save_settings, name="save_settings"),
    path("create/", views.create_manual, name="create_manual"),
    path("<int:run_id>/download/", views.download, name="download"),
    path("restore/", views.restore, name="restore"),
]
