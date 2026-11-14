from django.urls import path

from . import views

app_name = "printcenter"

urlpatterns = [
    path("", views.center, name="center"),
    path("tickets/new/", views.create_ticket, name="create_ticket"),
    path("tickets/<int:job_id>/", views.preview, name="preview"),
    path("tickets/<int:job_id>/cancel/", views.cancel, name="cancel"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/save/", views.save_settings, name="save_settings"),
    path("calendar/add/", views.add_calendar_block, name="add_calendar_block"),
    path(
        "calendar/<int:block_id>/delete/",
        views.delete_calendar_block,
        name="delete_calendar_block",
    ),
]
