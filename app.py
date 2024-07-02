import os
from functools import wraps  # Add this line
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Discord OAuth2 credentials
CLIENT_ID = "1257410612024053811"
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback"

# Discord API endpoints
DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_URL = "https://discord.com/api"

# Admin and Streamer Discord IDs
ADMIN_IDS = ["341560715615797251", "239871840691027969", "270602805818032129", "800712011439669258"]
STREAMER_IDS = ["239871840691027969", "341560715615797251"]

# Video queue
video_queue = []

banned_users = set()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "token" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_info" not in session or session["user_info"]["id"] not in ADMIN_IDS:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def streamer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_info" not in session or session["user_info"]["id"] not in STREAMER_IDS:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


user_submissions = {}
MAX_SUBMISSIONS = 3


@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    if request.method == "POST":
        user_id = session["user_info"]["id"]

        if user_id in banned_users:
            flash("You are banned from submitting videos.", "error")
            return redirect(url_for("home"))

        # Check if user has reached the submission limit
        if user_submissions.get(user_id, 0) >= MAX_SUBMISSIONS:
            flash("You have reached the maximum number of video submissions.", "error")
            return redirect(url_for("home"))

        youtube_url = request.form.get("youtube_url")
        start_min = int(request.form.get("start_min", 0))
        start_sec = int(request.form.get("start_sec", 0))
        end_min = int(request.form.get("end_min", 0))
        end_sec = int(request.form.get("end_sec", 0))

        video_id = extract_video_id(youtube_url)
        if not video_id:
            flash("Invalid YouTube URL", "error")
            return redirect(url_for("home"))

        start_time = start_min * 60 + start_sec
        end_time = end_min * 60 + end_sec

        video_info = get_video_info(video_id)
        user_info = session["user_info"]

        video_queue.append(
            {
                "video_id": video_id,
                "start_time": start_time,
                "end_time": end_time,
                "video_info": video_info,
                "user_info": user_info,
            }
        )

        # Increment user's submission count
        user_submissions[user_id] = user_submissions.get(user_id, 0) + 1

        flash("Video added to queue", "success")
        return redirect(url_for("home"))

    return render_template(
        "home.html", submissions_left=MAX_SUBMISSIONS - user_submissions.get(session["user_info"]["id"], 0)
    )


@app.route("/login")
def login():
    return redirect(
        f"{DISCORD_AUTH_URL}?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"
    )


@app.route("/callback")
def callback():
    code = request.args.get("code")
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(DISCORD_TOKEN_URL, data=data, headers=headers)
    r.raise_for_status()
    session["token"] = r.json()["access_token"]
    session["user_info"] = get_discord_user_info(session["token"])
    return redirect(url_for("home"))


@app.route("/delete_from_queue/<int:queue_number>", methods=["POST"])
@login_required
@admin_required
def delete_from_queue(queue_number):
    if 0 <= queue_number < len(video_queue):
        del video_queue[queue_number]
        flash("Video removed from queue", "success")
    else:
        flash("Invalid queue number", "error")
    return redirect(url_for("queue_management"))


@app.route("/queue")
@login_required
@admin_required
def queue_management():
    return render_template("queue_management.html", video_queue=video_queue)


@app.route("/ban_user/<string:user_id>", methods=["POST"])
@login_required
@admin_required
def ban_user(user_id):
    global video_queue
    banned_users.add(user_id)

    # Remove all videos from the banned user
    video_queue = [video for video in video_queue if video["user_info"]["id"] != user_id]

    flash(f"User {user_id} has been banned and their videos removed from the queue.", "success")
    return redirect(url_for("queue_management"))


@app.route("/player")
@login_required
@streamer_required
def video_player():
    if video_queue:
        video = video_queue[0]
        queue_length = len(video_queue)
    else:
        video = None
        queue_length = 0
    return render_template("video_player.html", video=video, queue_length=queue_length)


@app.route("/next_video", methods=["POST"])
@login_required
@streamer_required
def next_video():
    if video_queue:
        played_video = video_queue.pop(0)
        user_id = played_video["user_info"]["id"]
    return redirect(url_for("video_player"))


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


def get_video_info(video_id):
    # This is a placeholder. In a real application, you'd use the YouTube Data API
    # to get actual video information, including age restrictions.
    return {
        "title": "Sample Video Title",
        "age_restricted": False,
    }


def get_discord_user_info(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{DISCORD_API_URL}/users/@me", headers=headers)
    r.raise_for_status()
    user_info = r.json()
    return {"id": user_info["id"], "username": user_info["username"], "discriminator": user_info["discriminator"]}


if __name__ == "__main__":
    app.run(debug=True, port=8080)
