from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.home, name="home"),
    path("children/new/", views.child_create, name="child_create"),
    path("children/<int:profile_id>/avatar/", views.child_avatar, name="child_avatar"),
]
