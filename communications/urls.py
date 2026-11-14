from django.urls import path

from . import views

app_name = "communications"

urlpatterns = [
    path("", views.index, name="index"),
    path("messages/", views.sent_messages, name="sent_messages"),
    path("inbox/", views.message_inbox, name="message_inbox"),
    path(
        "messages/<int:recipient_id>/<str:action>/",
        views.message_read,
        name="message_read",
    ),
    path("notifications/", views.notification_list, name="notification_list"),
    path(
        "notifications/<int:notification_id>/<str:action>/",
        views.notification_read,
        name="notification_read",
    ),
]
