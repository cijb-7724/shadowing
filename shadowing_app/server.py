from __future__ import annotations

import json
import mimetypes
import argparse
import importlib.util
import shutil
import threading
import traceback
import uuid
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import load_config
from .enrichment import ollama_is_ready
from .pipeline import build_lesson
from .storage import Store
from .youtube import extract_video_id


class JobRunner:
    def __init__(self, config: dict, store: Store):
        self.config = config
        self.store = store
        self.lock = threading.Lock()

    def create(self, url: str) -> dict:
        video_id = extract_video_id(url)
        job = {
            "id": uuid.uuid4().hex[:12],
            "videoId": video_id,
            "url": url,
            "status": "queued",
            "stage": "queued",
            "message": "処理を開始します",
            "progress": 0,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
        self.store.save_job(job)
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"shadowing-{video_id}").start()
        return job

    def _update(self, job: dict, stage: str, message: str, progress: int) -> None:
        with self.lock:
            job.update({
                "status": "running",
                "stage": stage,
                "message": message,
                "progress": progress,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            })
            self.store.save_job(job)

    def _run(self, job: dict) -> None:
        try:
            lesson = build_lesson(job["url"], self.config, lambda stage, message, value: self._update(job, stage, message, value))
            self.store.save_draft(lesson)
            job.update({
                "status": "review",
                "stage": "review",
                "message": "生成完了。内容を確認して公開してください",
                "progress": 100,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as error:  # Job errors must be visible from the admin UI.
            job.update({
                "status": "failed",
                "stage": "failed",
                "message": str(error),
                "error": str(error),
                "debug": traceback.format_exc(),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            })
        self.store.save_job(job)


def make_handler(config: dict, store: Store, runner: JobRunner):
    root: Path = config["root"]

    class Handler(BaseHTTPRequestHandler):
        server_version = "ShadowingLocal/0.1"

        def log_message(self, fmt: str, *args) -> None:
            print(f"[{self.log_date_time_string()}] {fmt % args}")

        def _json(self, value, status=HTTPStatus.OK) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 8_000_000:
                raise ValueError("送信データが大きすぎます。")
            return json.loads(self.rfile.read(length) or b"{}")

        def _serve_static(self, request_path: str) -> None:
            relative = unquote(request_path.lstrip("/") or "index.html")
            if relative == "admin":
                relative = "admin/index.html"
            candidate = (root / relative).resolve()
            if root not in candidate.parents and candidate != root:
                return self.send_error(HTTPStatus.FORBIDDEN)
            if candidate.is_dir():
                candidate = candidate / "index.html"
            if not candidate.is_file() or any(part.startswith(".shadowing-work") for part in candidate.parts):
                return self.send_error(HTTPStatus.NOT_FOUND)
            content = candidate.read_bytes()
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/status":
                return self._json({
                    "ytDlp": bool(shutil.which("yt-dlp")),
                    "ffmpeg": bool(shutil.which("ffmpeg")),
                    "whisper": importlib.util.find_spec("faster_whisper") is not None,
                    "wordfreq": importlib.util.find_spec("wordfreq") is not None,
                    "ollama": ollama_is_ready(config["ollama"]["url"], config["ollama"]["model"]),
                    "ollamaModel": config["ollama"]["model"],
                })
            if path == "/api/jobs":
                return self._json(store.jobs())
            if path.startswith("/api/jobs/"):
                job = store.job(path.rsplit("/", 1)[-1])
                return self._json(job, HTTPStatus.OK if job else HTTPStatus.NOT_FOUND)
            if path.startswith("/api/drafts/"):
                draft = store.draft(path.rsplit("/", 1)[-1])
                return self._json(draft, HTTPStatus.OK if draft else HTTPStatus.NOT_FOUND)
            self._serve_static(path)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                if path == "/api/jobs":
                    job = runner.create(str(self._body().get("url", "")))
                    return self._json(job, HTTPStatus.ACCEPTED)
                if path.startswith("/api/retry/"):
                    previous = store.job(path.rsplit("/", 1)[-1])
                    if not previous:
                        return self._json({"error": "元のジョブが見つかりません。"}, HTTPStatus.NOT_FOUND)
                    job = runner.create(previous["url"])
                    return self._json(job, HTTPStatus.ACCEPTED)
                if path.startswith("/api/publish/"):
                    video_id = path.rsplit("/", 1)[-1]
                    draft = store.draft(video_id)
                    if not draft:
                        return self._json({"error": "下書きがありません。"}, HTTPStatus.NOT_FOUND)
                    store.publish(draft)
                    return self._json({"ok": True, "videoId": video_id})
                return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, json.JSONDecodeError) as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def do_PUT(self) -> None:
            path = urlparse(self.path).path
            if not path.startswith("/api/drafts/"):
                return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            video_id = path.rsplit("/", 1)[-1]
            try:
                draft = self._body()
                if draft.get("id") != video_id or not isinstance(draft.get("sentences"), list):
                    raise ValueError("下書きデータの形式が正しくありません。")
                store.save_draft(draft)
                return self._json({"ok": True})
            except (ValueError, json.JSONDecodeError) as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Shadowing admin server.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the admin page automatically.")
    parser.add_argument("--port", type=int, help="Override the configured port.")
    arguments = parser.parse_args()
    config = load_config()
    if arguments.port is not None:
        config["port"] = arguments.port
    store = Store(config["root"], config["workDir"])
    runner = JobRunner(config, store)
    server = ThreadingHTTPServer((config["host"], int(config["port"])), make_handler(config, store, runner))
    url = f"http://{config['host']}:{config['port']}/admin/"
    print(f"Shadowing admin: {url}")
    if not arguments.no_browser:
        threading.Timer(.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
