from django.urls import path
from . import views

urlpatterns = [
    path("alexa/", views.alexa_webhook, name="alexa_webhook"),
]