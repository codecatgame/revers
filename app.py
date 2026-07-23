"""
Реверс — сайт для завантаження аудіо за посиланням.
Запуск:
    pip install -r requirements.txt
    python app.py
Потім відкрити http://127.0.0.1:5000

Кожен відвідувач отримує анонімний ідентифікатор у cookie (без реєстрації
й пароля) — його файли зберігаються в окремій підпапці downloads/<uid>/
і не видні іншим відвідувачам.
"""

import os
import re
import uuid
import sys
import secrets
import subprocess
from datetime import timedelta
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, session, abort
)
from flask_cors import CORS
import static_ffmpeg
static_ffmpeg.add_paths()

app = Flask(__name__, template_folder='.')
CORS(app)
# У продакшні обов'язково задай постійний секрет через змінну середовища,
# інакше після кожного перезапуску сервера всі старі cookie-сесії "зламаються"
# і люди побачать порожню полицю (хоч файли на диску й лишаться).
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(days=365)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
UID_RE = re.compile(r"^[0-9a-f]{24}$")

# формат імені файлу на диску: "Виконавець ~ Назва [job_id].mp3"
NAME_RE = re.compile(r"^(?P<artist>.+?) ~ (?P<title>.+) \[[0-9a-f]{8}\]$")
JOBTAG_RE = re.compile(r"\s\[[0-9a-f]{8}\]$")


def get_user_id() -> str:
    """Анонімний ідентифікатор відвідувача, зберігається в cookie сесії."""
    uid = session.get("uid")
    if not uid or not UID_RE.match(uid):
        uid = secrets.token_hex(12)
        session["uid"] = uid
        session.permanent = True
    return uid


def user_dir(uid: str) -> str:
    path = os.path.join(DOWNLOAD_DIR, uid)
    os.makedirs(path, exist_ok=True)
    return path


def parse_track(filename: str):
    """Витягує (виконавець, назва) з імені файлу для показу на сторінці."""
    stem = os.path.splitext(filename)[0]
    match = NAME_RE.match(stem)
    if match:
        artist = match.group("artist").strip()
        title = match.group("title").strip()
        return artist or "Невідомий виконавець", title or stem
    # запасний варіант, якщо формат не співпав
    cleaned = JOBTAG_RE.sub("", stem).strip()
    return "Невідомий виконавець", cleaned or stem


@app.route("/")
def index():
    get_user_id()  # видаємо cookie одразу при першому візиті
    return render_template("index.html")


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify(ok=False, error="Посилання порожнє."), 400
    if not URL_RE.match(url):
        return jsonify(ok=False, error="Це не схоже на посилання."), 400

    uid = get_user_id()
    my_dir = user_dir(uid)

    before = set(os.listdir(my_dir))

    # унікальний префікс, щоб уникнути конфліктів імен при паралельних запитах
    job_id = uuid.uuid4().hex[:8]
    out_template = os.path.join(my_dir, f"%(artist,uploader)s ~ %(title)s [{job_id}].%(ext)s")

    command = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", out_template,
        url,
    ]

    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired:
        return jsonify(ok=False, error="Занадто довго — спробуй інше посилання."), 504

    if result.returncode != 0:
        return jsonify(ok=False, error="Не вдалося обробити це посилання."), 502
                print(result.stdout)
        print(result.stderr)
    
        return jsonify(
            ok=False,
            error=result.stderr or result.stdout
        ), 502

    after = set(os.listdir(my_dir))
    new_files = [f for f in (after - before) if f.endswith(".mp3")]

    if not new_files:
        return jsonify(ok=False, error="Файл не з'явився. Перевір посилання."), 502

    filename = new_files[0]
    artist, title = parse_track(filename)
    return jsonify(
        ok=True, filename=filename, title=title, artist=artist,
        url=f"/files/{uid}/{filename}"
    )


@app.route("/api/library")
def api_library():
    uid = get_user_id()
    my_dir = user_dir(uid)

    files = [f for f in os.listdir(my_dir) if f.endswith(".mp3")]
    files.sort(
        key=lambda f: os.path.getmtime(os.path.join(my_dir, f)),
        reverse=True,
    )
    result = []
    for f in files:
        artist, title = parse_track(f)
        result.append({
            "name": f, "artist": artist, "title": title,
            "url": f"/files/{uid}/{f}"
        })
    return jsonify(files=result)


@app.route("/files/<uid>/<path:filename>")
def files(uid, filename):
    # доступ лише до власної папки — інший відвідувач не побачить твої файли,
    # навіть якщо вгадає посилання
    if session.get("uid") != uid:
        abort(403)
    return send_from_directory(user_dir(uid), filename, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
