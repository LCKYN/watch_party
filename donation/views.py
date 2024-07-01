from urllib.parse import parse_qs, urlparse

from django.shortcuts import render
from pytube import YouTube

from donation.forms import VideoForm


def video_details(request):
    video_title = None
    age_restricted = None
    video_duration = None
    video_id = None
    start_time_minutes = 0
    start_time_seconds = 0
    end_time_minutes = 0
    end_time_seconds = 0
    start_time_seconds_total = 0
    end_time_seconds_total = 0

    if request.method == "POST":
        form = VideoForm(request.POST)
        if form.is_valid():
            video_url = form.cleaned_data["video_url"]
            start_time_minutes = form.cleaned_data["start_time_minutes"] or 0
            start_time_seconds = form.cleaned_data["start_time_seconds"] or 0
            end_time_minutes = form.cleaned_data["end_time_minutes"] or 0
            end_time_seconds = form.cleaned_data["end_time_seconds"] or 0
            try:
                video = YouTube(video_url)
                video_title = video.title
                age_restricted = video.age_restricted
                video_duration = format_duration(video.length)
                video_id = extract_video_id(video_url)
                start_time_seconds_total = convert_to_seconds(start_time_minutes, start_time_seconds)
                end_time_seconds_total = convert_to_seconds(end_time_minutes, end_time_seconds)
            except Exception as e:
                print(f"Error: {str(e)}")
    else:
        form = VideoForm()

    return render(
        request,
        "video_details.html",
        {
            "form": form,
            "video_title": video_title,
            "age_restricted": age_restricted,
            "video_duration": video_duration,
            "start_time_minutes": start_time_minutes,
            "start_time_seconds": start_time_seconds,
            "end_time_minutes": end_time_minutes,
            "end_time_seconds": end_time_seconds,
            "video_id": video_id,
            "start_time_seconds_total": start_time_seconds_total,
            "end_time_seconds_total": end_time_seconds_total,
            "start_time": format_duration(start_time_seconds_total),
            "end_time": format_duration(end_time_seconds_total),
        },
    )


def convert_to_seconds(minutes, seconds):
    return minutes * 60 + seconds


def format_duration(duration):
    minutes, seconds = divmod(duration, 60)
    return f"{minutes:02d}:{seconds:02d}"


def extract_video_id(url):
    query = urlparse(url)
    if query.hostname == "youtu.be":
        return query.path[1:]
    if query.hostname in ("www.youtube.com", "youtube.com"):
        if query.path == "/watch":
            p = parse_qs(query.query)
            return p["v"][0]
        if query.path[:7] == "/embed/":
            return query.path.split("/")[2]
        if query.path[:3] == "/v/":
            return query.path.split("/")[2]
    return None
