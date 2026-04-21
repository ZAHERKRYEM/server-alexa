from django.urls import path
from . import views

urlpatterns = [
    path("alexa/", views.alexa_webhook, name="alexa_webhook"),
    path("login/", views.login_view, name="login"),
    path("authorize/", views.authorize_view, name="authorize"),
    path("token/", views.token_view, name="token"),
]