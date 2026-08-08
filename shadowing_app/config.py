from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8000,
    "playbackBufferSeconds": 1.0,
    "preferYouTubeCaptions": True,
    "captionLanguages": "en-orig,en,en-GB",
    "transcription": {
        "provider": "faster-whisper",
        "model": "small.en",
        "computeType": "int8",
    },
    "ollama": {
        "enabled": True,
        "url": "http://127.0.0.1:11434",
        "model": "qwen3:4b",
        "batchSize": 8,
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or ROOT / "shadowing.config.json"
    if not config_path.exists():
        return dict(DEFAULT_CONFIG)
    with config_path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    config = _merge(DEFAULT_CONFIG, loaded)
    config["root"] = ROOT
    config["workDir"] = ROOT / ".shadowing-work"
    config["dataDir"] = ROOT / "data" / "videos"
    return config
