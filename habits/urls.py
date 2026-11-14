from django.urls import path

from . import views

app_name = "habits"

urlpatterns = [
    path("", views.template_list, name="template_list"),
    path("new/", views.template_create, name="template_create"),
    path("<int:template_id>/edit/", views.template_edit, name="template_edit"),
    path(
        "<int:template_id>/suspension/",
        views.template_toggle_suspension,
        name="template_toggle_suspension",
    ),
    path("<int:template_id>/archive/", views.template_archive, name="template_archive"),
    path("planning/", views.planning, name="planning"),
    path("planning/mine/", views.my_planning, name="my_planning"),
    path("planning/submit/<int:occurrence_id>/", views.submit, name="submit"),
    path("validation/", views.validation_list, name="validation_list"),
    path(
        "validation/<int:occurrence_id>/<str:decision>/",
        views.decide,
        name="decide",
    ),
]
