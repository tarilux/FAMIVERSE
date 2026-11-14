from django.urls import path

from . import views

app_name = "rewards"

urlpatterns = [
    path("", views.index, name="index"),
    path("catalog/", views.catalog, name="catalog"),
    path("new/", views.reward_create, name="reward_create"),
    path("<int:reward_id>/edit/", views.reward_edit, name="reward_edit"),
    path("<int:reward_id>/archive/", views.reward_archive, name="reward_archive"),
    path("shop/", views.shop, name="shop"),
    path("shop/<int:reward_id>/request/", views.request_reward_view, name="request"),
    path("requests/", views.request_list, name="request_list"),
    path(
        "requests/<int:request_id>/<str:decision>/",
        views.decide_request,
        name="decide_request",
    ),
]
