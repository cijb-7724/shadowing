from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


class Store:
    def __init__(self, root: Path, work_dir: Path):
        self.root = root
        self.work_dir = work_dir
        self.drafts_dir = work_dir / "drafts"
        self.jobs_dir = work_dir / "jobs"
        self.published_dir = root / "data" / "videos"
        for directory in (self.drafts_dir, self.jobs_dir, self.published_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def save_job(self, job: dict[str, Any]) -> None:
        atomic_write_json(self.jobs_dir / f"{job['id']}.json", job)

    def jobs(self) -> list[dict[str, Any]]:
        jobs = [read_json(path) for path in self.jobs_dir.glob("*.json")]
        return sorted((job for job in jobs if job), key=lambda item: item.get("createdAt", ""), reverse=True)

    def job(self, job_id: str) -> dict[str, Any] | None:
        return read_json(self.jobs_dir / f"{job_id}.json")

    def save_draft(self, lesson: dict[str, Any]) -> None:
        atomic_write_json(self.drafts_dir / f"{lesson['id']}.json", lesson)

    def draft(self, video_id: str) -> dict[str, Any] | None:
        return read_json(self.drafts_dir / f"{video_id}.json")

    def publish(self, lesson: dict[str, Any]) -> None:
        lesson["generatedAt"] = lesson.get("generatedAt") or datetime.now(timezone.utc).isoformat()
        atomic_write_json(self.published_dir / f"{lesson['id']}.json", lesson)
        self.save_draft(lesson)
        self.rebuild_manifest()
        self.mark_published(lesson["id"])

    def mark_published(self, video_id: str) -> None:
        """Mark successful generation jobs as published for a video."""
        for job in self.jobs():
            if job.get("videoId") != video_id or job.get("status") != "review":
                continue
            job.update({
                "status": "published",
                "stage": "published",
                "message": "公開済み。動画一覧に反映しました",
                "progress": 100,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            })
            self.save_job(job)

    def rebuild_manifest(self) -> list[dict[str, Any]]:
        existing = read_json(self.root / "data" / "videos.json", [])
        existing_order = {item["id"]: index for index, item in enumerate(existing)}
        items = []
        for path in self.published_dir.glob("*.json"):
            lesson = read_json(path)
            if not lesson:
                continue
            items.append({
                "id": lesson["id"],
                "title": lesson["title"],
                "sentenceCount": len(lesson.get("sentences", [])),
                "generatedAt": lesson.get("generatedAt"),
            })
        items.sort(key=lambda item: existing_order.get(item["id"], -1))
        atomic_write_json(self.root / "data" / "videos.json", items)
        return items
