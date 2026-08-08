from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


SYSTEM_PROMPT = """Translate every English sentence into natural, faithful Japanese for a shadowing learner.
Keep IDs unchanged. Do not explain or summarize. Return only JSON matching the supplied schema."""

WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
VOCAB_EXCLUSIONS = {
    "because", "before", "between", "different", "during", "everything",
    "however", "nothing", "really", "something", "through", "together",
    "without", "yourself", "themselves", "another", "already", "always",
}


RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "jp": {"type": "string"},
                },
                "required": ["id", "jp"],
            },
        }
    },
    "required": ["items"],
}


class OllamaUnavailable(RuntimeError):
    pass


def ollama_is_ready(base_url: str, model: str | None = None) -> bool:
    try:
        with urlopen(base_url.rstrip("/") + "/api/tags", timeout=1.5) as response:
            if response.status != 200:
                return False
            if model is None:
                return True
            payload = json.load(response)
            installed = {
                str(item.get("name") or item.get("model") or "")
                for item in payload.get("models", [])
            }
            return model in installed or f"{model}:latest" in installed
    except (OSError, URLError, ValueError):
        return False


def _request_batch(base_url: str, model: str, sentences: list[dict]) -> list[dict]:
    user_payload = [{"id": item["id"], "en": item["en"]} for item in sentences]
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": RESULT_SCHEMA,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "options": {
            "temperature": 0.1,
            "num_predict": min(1200, max(256, len(sentences) * 100)),
        },
    }
    request = Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=600) as response:
            result = json.load(response)
    except (OSError, URLError) as error:
        raise OllamaUnavailable("Ollamaに接続できません。`ollama serve` を確認してください。") from error
    try:
        return json.loads(result["message"]["content"])["items"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("Ollamaから期待したJSONを取得できませんでした。") from error


def _request_candidate_glosses(base_url: str, model: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": len(candidates),
                "maxItems": len(candidates),
                "items": {
                    "type": "object",
                    "properties": {
                        "sentenceId": {"type": "integer"},
                        "term": {"type": "string"},
                        "meaning": {"type": "string"},
                        "level": {"type": "string", "enum": ["B1", "B2", "C1", "C2", "technical"]},
                        "note": {"type": "string"},
                    },
                    "required": ["sentenceId", "term", "meaning", "level", "note"],
                },
            }
        },
        "required": ["items"],
    }
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": schema,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Give a concise context-appropriate Japanese meaning and CEFR estimate for every supplied English term. "
                    "Return exactly one item per input, preserving sentenceId and term. Return only schema-valid JSON."
                ),
            },
            {"role": "user", "content": json.dumps(candidates, ensure_ascii=False)},
        ],
        "options": {
            "temperature": 0.0,
            "num_predict": min(2048, max(256, len(candidates) * 100)),
        },
    }
    request = Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=600) as response:
            result = json.load(response)
        return json.loads(result["message"]["content"])["items"]
    except (OSError, URLError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("語彙候補の日本語解説を生成できませんでした。") from error


def enrich_sentences(sentences: list[dict], config: dict[str, Any], progress=None) -> list[dict]:
    if not config.get("enabled", True):
        for sentence in sentences:
            sentence["needsReview"] = True
        return sentences
    base_url = config["url"]
    if not ollama_is_ready(base_url, config["model"]):
        raise OllamaUnavailable(
            f"Ollamaまたはモデル {config['model']} を利用できません。"
            "READMEに従って準備するか、設定で無効にしてください。"
        )
    batch_size = max(1, int(config.get("batchSize", 8)))
    by_id = {item["id"]: item for item in sentences}
    for offset in range(0, len(sentences), batch_size):
        batch = sentences[offset:offset + batch_size]
        generated = _request_translation_resilient(base_url, config["model"], batch)
        for item in generated:
            target = by_id.get(item.get("id"))
            if not target:
                continue
            target["jp"] = str(item.get("jp", "")).strip()
            target["vocab"] = []
            if not target["jp"]:
                target["needsReview"] = True
        _ensure_candidate_vocab(batch, base_url, config["model"])
        if progress:
            progress(min(offset + len(batch), len(sentences)), len(sentences))
    _deduplicate_and_move_vocab(sentences)
    return sentences


def _request_translation_resilient(base_url: str, model: str, sentences: list[dict]) -> list[dict]:
    try:
        generated = _request_batch(base_url, model, sentences)
    except RuntimeError:
        if len(sentences) == 1:
            return _request_batch(base_url, model, sentences)
        middle = len(sentences) // 2
        return (
            _request_translation_resilient(base_url, model, sentences[:middle])
            + _request_translation_resilient(base_url, model, sentences[middle:])
        )

    expected_ids = {item["id"] for item in sentences}
    valid = {
        item.get("id"): item for item in generated
        if isinstance(item, dict)
        and item.get("id") in expected_ids
        and str(item.get("jp", "")).strip()
    }
    missing = [item for item in sentences if item["id"] not in valid]
    if not missing:
        return [valid[item["id"]] for item in sentences]
    if len(sentences) == 1:
        retried = _request_batch(base_url, model, sentences)
        if not any(
            isinstance(item, dict)
            and item.get("id") == sentences[0]["id"]
            and str(item.get("jp", "")).strip()
            for item in retried
        ):
            raise RuntimeError("Ollamaが翻訳を返しませんでした。")
        return retried
    return list(valid.values()) + _request_translation_resilient(base_url, model, missing)


def _ensure_candidate_vocab(sentences: list[dict], base_url: str, model: str) -> None:
    requests = []
    for sentence in sentences:
        existing = {item["term"].casefold() for item in sentence.get("vocab", [])}
        for term in _candidate_terms(sentence["en"]):
            if term.casefold() not in existing:
                requests.append({"sentenceId": sentence["id"], "term": term, "context": sentence["en"]})
    if not requests:
        return
    generated = []
    for offset in range(0, len(requests), 10):
        chunk = requests[offset:offset + 10]
        try:
            generated.extend(_request_candidate_glosses(base_url, model, chunk))
        except RuntimeError:
            for request in chunk:
                try:
                    generated.extend(_request_candidate_glosses(base_url, model, [request]))
                except RuntimeError:
                    pass
    lookup = {
        (int(item.get("sentenceId", -1)), str(item.get("term", "")).casefold()): item
        for item in generated if isinstance(item, dict)
    }
    by_id = {sentence["id"]: sentence for sentence in sentences}
    for requested in requests:
        target = by_id[requested["sentenceId"]]
        item = lookup.get((requested["sentenceId"], requested["term"].casefold()))
        if item is None:
            requested_key = requested["term"].casefold()
            item = next((
                generated_item for generated_item in generated
                if isinstance(generated_item, dict)
                and int(generated_item.get("sentenceId", -1)) == requested["sentenceId"]
                and requested_key in str(generated_item.get("term", "")).casefold()
            ), None)
        if item and str(item.get("meaning", "")).strip():
            target["vocab"].append({
                "term": requested["term"],
                "meaning": str(item["meaning"]).strip(),
                "level": str(item.get("level", "B1")).strip(),
                "note": str(item.get("note", "")).strip(),
            })
        else:
            target["vocab"].append({
                "term": requested["term"],
                "meaning": "意味を確認してください",
                "level": "B1+",
                "note": "ローカル頻度辞書による候補",
            })
            target["needsReview"] = True


def _clean_vocab(items: list) -> list[dict]:
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "")).strip()
        meaning = str(item.get("meaning", "")).strip()
        if not term or not meaning:
            continue
        result.append({
            "term": term,
            "meaning": meaning,
            "level": str(item.get("level", "")).strip(),
            "note": str(item.get("note", "")).strip(),
        })
    return result


def _candidate_terms(text: str) -> list[str]:
    """Use local frequency data to keep difficult words from being silently omitted."""
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return []
    candidates = []
    for match in WORD_RE.finditer(text):
        surface = match.group(0)
        term = surface.casefold().replace("’", "'")
        if len(term) < 6 or term in VOCAB_EXCLUSIONS or "'" in term:
            continue
        if surface[0].isupper() and match.start() != 0:
            continue
        frequency = zipf_frequency(term, "en")
        if frequency == 0 or frequency < 4.55:
            candidates.append(surface)
    return list(dict.fromkeys(candidates))


def _deduplicate_and_move_vocab(sentences: list[dict]) -> None:
    candidates: dict[str, dict] = {}
    for sentence in sentences:
        for item in sentence.get("vocab", []):
            key = re.sub(r"\s+", " ", item["term"].casefold()).strip()
            candidates.setdefault(key, item)
        sentence["vocab"] = []
    for key, item in candidates.items():
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(key)}(?![A-Za-z])", re.IGNORECASE)
        target = next((sentence for sentence in sentences if pattern.search(sentence["en"])), None)
        if target:
            target["vocab"].append(item)
