from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


class YouTubeError(RuntimeError):
    pass


def extract_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if host not in YOUTUBE_HOSTS:
        raise ValueError("youtube.com または youtu.be のURLを入力してください。")
    if host.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
        video_id = parsed.path.strip("/").split("/")[1]
    else:
        video_id = ""
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("YouTube動画IDをURLから取得できませんでした。")
    return video_id


def _run(arguments: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(arguments, check=True, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as error:
        raise YouTubeError(f"{arguments[0]} が見つかりません。READMEのセットアップを確認してください。") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error)).strip().splitlines()[-1]
        raise YouTubeError(detail) from error


def metadata(url: str) -> dict:
    result = _run(["yt-dlp", "--dump-single-json", "--skip-download", "--no-playlist", url])
    data = json.loads(result.stdout)
    return {
        "id": data["id"],
        "title": data.get("title") or data["id"],
        "duration": data.get("duration"),
        "channel": data.get("channel") or data.get("uploader"),
        "webpageUrl": data.get("webpage_url") or url,
    }


def download_captions(url: str, directory: Path, languages: str) -> Path | None:
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "captions"
    try:
        _run([
            "yt-dlp", "--skip-download", "--no-playlist",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", languages, "--sub-format", "json3",
            "-o", str(output), url,
        ])
    except YouTubeError:
        # yt-dlp may fail on a secondary requested track after successfully
        # writing the original English track. Prefer that usable result.
        if not list(directory.glob("captions*.json3")):
            raise
    candidates = sorted(directory.glob("captions*.json3"), key=lambda path: ("orig" not in path.name, len(path.name)))
    return candidates[0] if candidates else None


def download_audio(url: str, directory: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise YouTubeError("ffmpeg が見つかりません。")
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "audio.%(ext)s"
    _run([
        "yt-dlp", "--no-playlist", "-x", "--audio-format", "wav",
        "--postprocessor-args", "ffmpeg:-ac 1 -ar 16000",
        "-o", str(output), url,
    ], timeout=1800)
    audio = directory / "audio.wav"
    if not audio.exists():
        raise YouTubeError("音声ファイルを作成できませんでした。")
    return audio
