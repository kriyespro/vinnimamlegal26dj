from django.urls import path

from . import views

urlpatterns = [
    path("portal", views.portal, name="portal"),
    path("portal/logout", views.portal_logout, name="portal_logout"),
    path("portal/reset/<str:uidb64>/<str:token>", views.portal_reset, name="portal_reset"),
]
