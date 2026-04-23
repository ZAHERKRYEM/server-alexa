from django.urls import path
from . import views

urlpatterns = [
    # ── Alexa OAuth ──
    path("alexa/",      views.alexa_webhook,             name="alexa_webhook"),
    path("authorize/",  views.authorize_view,             name="authorize"),
    path("token/",      views.token_view,                 name="token"),
    path("login/",      views.login_view,                 name="login"),

    # ── App Link (Android) ──
    path("alexa-login/", views.alexa_login_redirect_view, name="alexa_login_redirect"),

    # ── Flutter App API ──
    path("api/login/",         views.app_login_view,      name="app_login"),
    path("api/app-authorize/", views.app_authorize_view,  name="app_authorize"),

    # ── Devices API ──
    path("api/devices/",           views.devices_view,       name="devices"),
    path("api/devices/<int:device_id>/", views.device_detail_view, name="device_detail"),

    # ── Android App Links ──
    path(".well-known/assetlinks.json", views.assetlinks_view, name="assetlinks"),
]