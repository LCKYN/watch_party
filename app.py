import os
import time
import uuid
from functools import wraps  # Add this line
from threading import Lock, RLock
from time import time
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

queue_lock = RLock()
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Discord OAuth2 credentials
CLIENT_ID = "1257410612024053811"
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIRECT_URI = "http://greankingdom.com/callback"
# REDIRECT_URI = "http://127.0.0.1:8080/callback"

GUILD_ID = "939695971384844338"  # FifaTargrean server

# Discord API endpoints
DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_URL = "https://discord.com/api"

# Admin and Streamer Discord IDs
ADMIN_IDS = [
    "239871840691027969",
    "270602805818032129",
    "274728216436932614",
    "341560715615797251",
    "569874307933798429",
    "800712011439669258",
]
STREAMER_IDS = ["239871840691027969", "341560715615797251"]

# Video queue
video_queue = []
banned_users = set()
user_submissions = {}
last_submission_times = {}
MAX_SUBMISSION_DURATION = 300  # 5 minutes in seconds


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "token" not in session:
            return redirect(url_for("login"))
        if not session.get("in_guild", False):
            return redirect(url_for("not_in_guild"))
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


@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    user_id = session["user_info"]["id"]

    if request.method == "POST":
        user_ip = request.remote_addr

        current_time = time()
        last_submission_time = last_submission_times.get(user_id, 0)

        if user_id in banned_users:
            flash("You are banned from submitting videos.", "error")
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
        duration = end_time - start_time

        # Check if user has enough submission duration available
        remaining_duration = user_submissions.get(user_id, MAX_SUBMISSION_DURATION)

        if duration > remaining_duration:
            flash(
                f"Video duration ({duration} seconds) exceeds your remaining submission time ({remaining_duration} seconds). Please choose a shorter clip.",
                "error",
            )
            return redirect(url_for("home"))

        video_info = get_video_info(video_id)
        user_info = session["user_info"]

        with queue_lock:
            video_queue.append(
                {
                    "id": str(uuid.uuid4()),
                    "video_id": video_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "video_info": video_info,
                    "user_info": user_info,
                    "user_ip": user_ip,
                    "user_id": user_id,
                    "passed": False,
                    "display_name": session["display_name"],
                }
            )

        # Update user's remaining submission time
        user_submissions[user_id] = remaining_duration - duration

        last_submission_times[user_id] = current_time
        flash("Video added to queue", "success")
        return redirect(url_for("home"))

    # Get remaining submission time for the user
    remaining_duration = user_submissions.get(user_id, MAX_SUBMISSION_DURATION)

    # Calculate time left before next submission
    current_time = time()
    last_submission_time = last_submission_times.get(user_id, 0)
    cooldown_left = max(0, 5 - (current_time - last_submission_time))

    return render_template("home.html", remaining_duration=remaining_duration, cooldown_left=cooldown_left)


@app.route("/login")
def login():
    return redirect(
        f"{DISCORD_AUTH_URL}?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds%20guilds.members.read"
    )


@app.route("/clear_queue", methods=["POST"])
@login_required
@admin_required
def clear_queue():
    global video_queue
    with queue_lock:
        video_queue.clear()
    flash("All videos have been removed from the queue.", "success")
    return redirect(url_for("admin"))


@app.route("/unban", methods=["POST"])
@login_required
@admin_required
def unban():
    to_unban = request.form.get("to_unban")
    if to_unban in banned_users:
        banned_users.remove(to_unban)
        flash(f"Successfully unbanned: {to_unban}", "success")
    else:
        flash(f"{to_unban} was not in the banned list.", "warning")
    return redirect(url_for("admin"))


@app.route("/admin", methods=["GET", "POST"])
@login_required
@admin_required
def admin():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "ban_user":
            user_id = request.form.get("user_id")
            banned_users.add(user_id)
            flash(f"User {user_id} has been banned.", "success")

        elif action == "ban_ip":
            ip_address = request.form.get("ip_address")
            banned_users.add(ip_address)
            flash(f"IP address {ip_address} has been banned.", "success")

        elif action == "clear_user_submissions":
            user_id = request.form.get("user_id")
            if isinstance(user_id, str):
                user_id = user_id.strip()
            if user_id in user_submissions:
                user_submissions[user_id] = MAX_SUBMISSION_DURATION
                flash(f"Submission time for user {user_id} has been reset to maximum.", "success")
            else:
                flash(f"No submissions found for user {user_id}.", "warning")

        elif action == "clear_all_submissions":
            user_submissions.clear()
            flash("All user submissions have been cleared.", "success")

    banned_user_ids = [b for b in banned_users if not b.replace(".", "").isdigit()]
    banned_ips = [b for b in banned_users if b.replace(".", "").isdigit()]

    return render_template(
        "admin.html",
        banned_user_ids=banned_user_ids,
        banned_ips=banned_ips,
        user_submissions=user_submissions,
        queue_length=len(video_queue),
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

    # Get the access token
    access_token = r.json()["access_token"]
    session["token"] = access_token

    # Get user info
    user_info = get_discord_user_info(access_token)
    session["user_info"] = user_info

    # Check if user is in the guild
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}  # You'll need to set up a bot and get its token
    guild_member_url = f"{DISCORD_API_URL}/guilds/{GUILD_ID}/members/{user_info['id']}"
    r = requests.get(guild_member_url, headers=headers)

    if r.status_code == 200:
        # User is in the guild
        session["in_guild"] = True

        if r.json()["nick"] is not None:
            session["display_name"] = r.json()["nick"]
        else:
            session["display_name"] = r.json()["user"]["global_name"]

        return redirect(url_for("home"))
    else:
        # User is not in the guild
        session["in_guild"] = False
        return redirect(url_for("not_in_guild"))


@app.route("/not_in_guild")
def not_in_guild():
    session.clear()
    return render_template("not_in_guild.html")


@app.route("/delete_from_queue/<string:video_id>", methods=["POST"])
@login_required
@admin_required
def delete_from_queue(video_id):
    with queue_lock:
        for index, video in enumerate(video_queue):
            if video["id"] == video_id:
                del video_queue[index]
                flash("Video removed from queue", "success")
                break
        else:
            flash("Video not found in queue", "error")
    return redirect(url_for("queue_management"))


@app.route("/queue")
@login_required
@admin_required
def queue_management():
    with queue_lock:
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


@app.route("/pass_video/<string:video_id>", methods=["POST"])
@login_required
@admin_required
def pass_video(video_id):
    with queue_lock:
        for video in video_queue:
            if video["id"] == video_id:
                video["passed"] = True
                flash("Video passed for playing", "success")
                break
        else:
            flash("Video not found in queue", "error")
    return redirect(url_for("queue_management"))


@app.route("/player")
@login_required
@streamer_required
def video_player():
    with queue_lock:
        passed_videos = [v for v in video_queue if v.get("passed", False)]
        if passed_videos:
            video = passed_videos[0]
            queue_length = len(passed_videos)
        else:
            video = None
            queue_length = 0
    return render_template("video_player.html", video=video, queue_length=queue_length)


@app.route("/next_video", methods=["POST"])
@login_required
@streamer_required
def next_video():
    with queue_lock:
        passed_videos = [v for v in video_queue if v.get("passed", False)]
        if passed_videos:
            played_video = passed_videos[0]
            video_queue.remove(played_video)
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
