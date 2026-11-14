from django.urls import path

from . import views

app_name = "missions"

urlpatterns = [
    path("", views.template_list, name="template_list"),
    path("categories/new/", views.category_create, name="category_create"),
    path("new/", views.template_create, name="template_create"),
    path("<int:template_id>/edit/", views.template_edit, name="template_edit"),
    path("<int:template_id>/archive/", views.template_archive, name="template_archive"),
    path("<int:template_id>/assign/", views.assign, name="assign"),
    path("mine/", views.my_missions, name="my_missions"),
    path("<int:occurrence_id>/submit/", views.submit, name="submit"),
    path("validation/", views.validation_list, name="validation_list"),
    path("validation/decide/", views.decide, name="decide"),
]
