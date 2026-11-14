from django.urls import path

from . import views

app_name = "progression"

urlpatterns = [
    path("mine/", views.my_progress, name="my_progress"),
    path("children/<int:child_id>/", views.child_progress, name="child_progress"),
    path(
        "children/<int:child_id>/adjust/",
        views.adjust_balance,
        name="adjust_balance",
    ),
]
