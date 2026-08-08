from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[’'][A-Za-z0-9]+)*(?:-[A-Za-z0-9]+)*|[^\w\s]", re.UNICODE)
NON_SPEECH_RE = re.compile(r"^\s*[\[(].*?[\])]\s*$")
END_PUNCTUATION = {".", "?", "!"}
NO_SPACE_BEFORE = {".", ",", "?", "!", ";", ":", "%", "’", "'"}


@dataclass
class TimedWord:
    text: str
    start: float
    end: float
    confidence: float | None = None


def _tokenize_chunk(text: str, start: float, end: float, confidence: float | None = None) -> list[TimedWord]:
    tokens = TOKEN_RE.findall(html.unescape(text).replace("\n", " "))
    if not tokens or NON_SPEECH_RE.match(" ".join(tokens)):
        return []
    duration = max(0.04, end - start)
    weights = [max(1, len(token.strip(".,?!;:"))) for token in tokens]
    total = sum(weights)
    cursor = start
    result = []
    for token, weight in zip(tokens, weights):
        token_end = min(end, cursor + duration * weight / total)
        result.append(TimedWord(token, cursor, token_end, confidence))
        cursor = token_end
    return result


def parse_json3(path: Path) -> list[TimedWord]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    words: list[TimedWord] = []
    previous_text = ""
    for event in payload.get("events", []):
        segments = event.get("segs") or []
        if not segments:
            continue
        event_start = float(event.get("tStartMs", 0)) / 1000
        event_end = event_start + max(float(event.get("dDurationMs", 1000)) / 1000, .1)
        event_text = "".join(str(segment.get("utf8", "")) for segment in segments).strip()
        if not event_text or event_text == previous_text or NON_SPEECH_RE.match(event_text):
            continue
        previous_text = event_text
        for index, segment in enumerate(segments):
            text = str(segment.get("utf8", ""))
            if not text.strip():
                continue
            start = event_start + float(segment.get("tOffsetMs", 0)) / 1000
            if index + 1 < len(segments):
                next_offset = float(segments[index + 1].get("tOffsetMs", event.get("dDurationMs", 1000))) / 1000
                end = event_start + next_offset
            else:
                end = event_end
            confidence = segment.get("acAsrConf")
            if confidence is not None:
                confidence = float(confidence) / 255 if float(confidence) > 1 else float(confidence)
            words.extend(_tokenize_chunk(text, start, max(start + .04, end), confidence))
    return _remove_immediate_duplicates(words)


def _remove_immediate_duplicates(words: list[TimedWord]) -> list[TimedWord]:
    result: list[TimedWord] = []
    for word in words:
        if result and word.text.casefold() == result[-1].text.casefold() and word.start <= result[-1].end + .05:
            if word.end > result[-1].end:
                result[-1].end = word.end
            continue
        result.append(word)
    return result


def _join_tokens(words: Iterable[TimedWord]) -> str:
    text = ""
    for word in words:
        token = word.text
        if not text or token in NO_SPACE_BEFORE or token.startswith(("'", "’")):
            text += token
        else:
            text += " " + token
    return text.strip()


def words_to_sentences(words: list[TimedWord], playback_buffer: float = 1.0) -> list[dict]:
    if not words:
        return []
    groups: list[list[TimedWord]] = []
    current: list[TimedWord] = []
    word_count = 0
    for index, word in enumerate(words):
        current.append(word)
        if re.match(r"[A-Za-z0-9]", word.text):
            word_count += 1
        next_word = words[index + 1] if index + 1 < len(words) else None
        pause = (next_word.start - word.end) if next_word else math.inf
        ends_sentence = word.text in END_PUNCTUATION
        next_starts_sentence = bool(next_word and next_word.text[:1].isupper())
        natural_pause = pause >= .85 and word_count >= 5 and next_starts_sentence
        # Keep unusually long, but properly punctuated source sentences intact.
        # This is only a last-resort guard for caption streams with no punctuation.
        too_long = word_count >= 50
        if ends_sentence or natural_pause or too_long or next_word is None:
            groups.append(current)
            current = []
            word_count = 0

    sentences = []
    for index, group in enumerate(groups):
        text = _join_tokens(group)
        if not text or NON_SPEECH_RE.match(text):
            continue
        if not re.search(r"[A-Za-z0-9]", text):
            if sentences:
                sentences[-1]["en"] += text
                sentences[-1]["end"] = round(group[-1].end, 3)
            continue
        start = group[0].start
        confidences = [word.confidence for word in group if word.confidence is not None]
        confidence = sum(confidences) / len(confidences) if confidences else None
        sentences.append({
            "id": len(sentences) + 1,
            "speechStart": round(start, 3),
            "playFrom": max(0, math.floor(start) - math.ceil(playback_buffer)),
            "end": round(group[-1].end, 3),
            "en": text,
            "jp": "",
            "vocab": [],
            "confidence": round(confidence, 3) if confidence is not None else None,
            "needsReview": confidence is not None and confidence < .55,
        })
    return sentences


def transcribe_with_faster_whisper(audio: Path, model_name: str, compute_type: str) -> list[TimedWord]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "字幕がない動画には faster-whisper が必要です。"
            " `python3 -m pip install faster-whisper` を実行してください。"
        ) from error

    model = WhisperModel(model_name, device="cpu", compute_type=compute_type)
    segments, _ = model.transcribe(
        str(audio), language="en", task="transcribe", word_timestamps=True,
        vad_filter=True, beam_size=5, condition_on_previous_text=True,
    )
    words: list[TimedWord] = []
    for segment in segments:
        for word in segment.words or []:
            words.append(TimedWord(word.word.strip(), float(word.start), float(word.end), float(word.probability)))
    return words
