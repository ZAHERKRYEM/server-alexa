from django.urls import path
from . import views

urlpatterns = [
    path("alexa/", views.alexa_webhook, name="alexa_webhook"),
    path("login/", views.login_view, name="login"),
    path("authorize/", views.authorize_view, name="authorize"),
    path("token/", views.token_view, name="token"),

        # ── App Link: Alexa يفتحه → Android يعترضه → يفتح Flutter ──
    path("alexa-login/", views.alexa_login_redirect_view, name="alexa_login_redirect"),

    # ── Flutter App API ──
    path("api/login/",         views.app_login_view,     name="app_login"),
    path("api/app-authorize/", views.app_authorize_view, name="app_authorize"),

    # ── Android App Links Verification ──
    path(".well-known/assetlinks.json", views.assetlinks_view, name="assetlinks"),
]