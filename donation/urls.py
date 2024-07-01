from django.urls import path

from donation.views import video_details

urlpatterns = [
    path("", video_details, name="video_details"),
]
