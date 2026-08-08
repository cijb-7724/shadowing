from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import transcript, youtube
from .enrichment import enrich_sentences


Progress = Callable[[str, str, int], None]


def build_lesson(url: str, config: dict, progress: Progress) -> dict:
    video_id = youtube.extract_video_id(url)
    work_dir: Path = config["workDir"] / "videos" / video_id
    work_dir.mkdir(parents=True, exist_ok=True)

    progress("metadata", "動画情報を取得しています", 5)
    info = youtube.metadata(url)

    timed_words = []
    source = ""
    if config.get("preferYouTubeCaptions", True):
        progress("captions", "英語字幕と単語時刻を取得しています", 15)
        caption_path = youtube.download_captions(url, work_dir, config.get("captionLanguages", "en-orig,en,en-GB"))
        if caption_path:
            timed_words = transcript.parse_json3(caption_path)
            source = "youtube-captions"

    if not timed_words:
        progress("audio", "字幕がないため音声を取得しています", 22)
        audio = youtube.download_audio(url, work_dir)
        progress("transcription", "ローカルWhisperで文字起こししています", 30)
        transcribe_config = config["transcription"]
        timed_words = transcript.transcribe_with_faster_whisper(
            audio, transcribe_config["model"], transcribe_config.get("computeType", "int8")
        )
        source = "faster-whisper"

    progress("segmentation", "単語時刻から文を組み立てています", 52)
    sentences = transcript.words_to_sentences(timed_words, float(config.get("playbackBufferSeconds", 1)))
    if not sentences:
        raise RuntimeError("英語の発話を検出できませんでした。")

    progress("enrichment", "日本語訳と高校レベル以上の語彙を生成しています", 58)
    enrich_sentences(
        sentences,
        config["ollama"],
        lambda done, total: progress("enrichment", f"日本語訳と語彙を生成中 ({done}/{total})", 58 + int(34 * done / total)),
    )

    progress("saving", "確認用データを保存しています", 96)
    return {
        "schemaVersion": 1,
        "id": info["id"],
        "title": info["title"],
        "sourceUrl": info["webpageUrl"],
        "channel": info.get("channel"),
        "duration": info.get("duration"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "transcriptSource": source,
        "sentences": sentences,
    }
