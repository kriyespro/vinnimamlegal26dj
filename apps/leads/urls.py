from django.urls import path

from . import views

urlpatterns = [path("enquire", views.enquire, name="enquire")]
