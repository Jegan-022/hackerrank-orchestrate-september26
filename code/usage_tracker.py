"""
usage_tracker.py — Tracks LLM API usage for the usage_report.
"""
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class UsageRecord:
    model: str
    provider: str
    call_type: str  # "image", "message", "explanation"
    input_tokens: int
    output_tokens: int
    cache_hit: bool


_records: List[UsageRecord] = []


def record_call(
    model: str,
    provider: str,
    call_type: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit: bool = False,
) -> None:
    _records.append(
        UsageRecord(model, provider, call_type, input_tokens, output_tokens, cache_hit)
    )


def get_summary() -> Dict:
    total_calls = len([r for r in _records if not r.cache_hit])
    cache_hits = len([r for r in _records if r.cache_hit])
    total_input = sum(r.input_tokens for r in _records if not r.cache_hit)
    total_output = sum(r.output_tokens for r in _records if not r.cache_hit)
    total_tokens = total_input + total_output
    # Group by model
    models: Dict[str, dict] = {}
    for r in _records:
        if r.cache_hit:
            continue
        key = f"{r.provider}/{r.model}"
        if key not in models:
            models[key] = {"provider": r.provider, "model": r.model, "calls": 0, "input_tokens": 0, "output_tokens": 0}
        models[key]["calls"] += 1
        models[key]["input_tokens"] += r.input_tokens
        models[key]["output_tokens"] += r.output_tokens
    return {
        "total_calls": total_calls,
        "cache_hits": cache_hits,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "per_model": models,
    }


def reset() -> None:
    _records.clear()
