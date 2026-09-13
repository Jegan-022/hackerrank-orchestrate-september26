"""
cache.py — Persistent SHA256-keyed cache for LLM/OCR results.
"""
import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from config import CACHE_DIR


def _ensure_dir(subdir: str) -> Path:
    d = CACHE_DIR / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_key(content: bytes, model: str, prompt_version: str) -> str:
    h = hashlib.sha256()
    h.update(content)
    h.update(model.encode())
    h.update(prompt_version.encode())
    return h.hexdigest()


def get_cached(subdir: str, content: bytes, model: str, prompt_version: str) -> Optional[dict]:
    """Return cached result or None."""
    key = _make_key(content, model, prompt_version)
    cache_file = _ensure_dir(subdir) / f"{key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                record = json.load(f)
            return record.get("result")
        except Exception:
            return None
    return None


def set_cached(
    subdir: str,
    content: bytes,
    model: str,
    prompt_version: str,
    result: Any,
    usage: Optional[dict] = None,
) -> None:
    """Store result in cache."""
    key = _make_key(content, model, prompt_version)
    cache_file = _ensure_dir(subdir) / f"{key}.json"
    record = {
        "cache_key": key,
        "model": model,
        "prompt_version": prompt_version,
        "input_hash": key,
        "result": result,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "usage": usage or {"input_tokens": 0, "output_tokens": 0},
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)


def get_cache_stats(subdir: str) -> dict:
    """Return hit/miss stats (counted during runtime, tracked separately)."""
    d = _ensure_dir(subdir)
    files = list(d.glob("*.json"))
    return {"cached_entries": len(files)}
