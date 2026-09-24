"""Score headlines with Jev: concurrent, retried, resumable by caller, with a mock for offline use."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass

from loguru import logger

from ridethewave.signals.jev_questions import HEADLINE_QUESTIONS, QUESTIONS_VERSION, headline_state


@dataclass(slots=True)
class HeadlineJob:
    key: str  # unique id for caching, e.g. f"{news_id}:{symbol}"
    symbol: str
    headline: str
    summary: str | None
    source: str | None
    symbols: list[str]


def flatten(answers: dict) -> dict:
    """Answer objects (SDK or raw dict) -> one flat dict of numbers and labels."""

    def get(a, name):
        return a.get(name) if isinstance(a, dict) else getattr(a, name)

    d = answers["direction"]
    probs = get(d, "probabilities")
    m = answers["materiality"]
    k = answers["kind"]
    return {
        "direction": get(d, "choice"),
        "direction_conf": float(get(d, "confidence")),
        "p_up": float(probs.get("up", 0.0)),
        "p_down": float(probs.get("down", 0.0)),
        "p_mixed": float(probs.get("mixed", 0.0)),
        "p_none": float(probs.get("none", 0.0)),
        "p_positive": float(get(answers["positive"], "noul")),
        "materiality": float(get(m, "score")),
        "materiality_conf": float(get(m, "confidence")),
        "kind": get(k, "choice"),
        "kind_conf": float(get(k, "confidence")),
        "p_stale": float(get(answers["stale"], "noul")),
        "p_toxic": float(get(answers["toxic"], "noul")),
        **_flatten_v2(answers, get),
    }


def _flatten_v2(answers: dict, get) -> dict:
    """The four questions added in 2026-09-24.1; absent from older scores."""
    if "event" not in answers:
        return {}
    e, sp = answers["event"], answers["surprise"]
    return {
        "p_relevant": float(get(answers["relevant"], "noul")),
        "event": get(e, "choice"),
        "event_conf": float(get(e, "confidence")),
        "surprise": float(get(sp, "score")),
        "surprise_conf": float(get(sp, "confidence")),
        "p_durable": float(get(answers["durable"], "noul")),
    }


def mock_answers(job: HeadlineJob) -> dict:
    h = int(hashlib.sha256((job.key + job.headline).encode()).hexdigest(), 16)
    labels = ["up", "down", "mixed", "none"]
    w = [((h >> (8 * i)) % 100) + 1 for i in range(4)]
    probs = {lab: x / sum(w) for lab, x in zip(labels, w, strict=True)}
    best = max(probs, key=probs.get)
    kinds = [
        "earnings_or_guidance",
        "product",
        "capital_action",
        "legal_regulatory",
        "macro_or_sector",
        "analyst_or_opinion",
        "list_or_roundup",
        "other",
    ]
    return {
        "direction": {"choice": best, "probabilities": probs, "confidence": probs[best]},
        "positive": {"noul": (h % 1000) / 1000},
        "materiality": {"score": ((h >> 40) % 200) / 100, "confidence": 0.5},
        "kind": {"choice": kinds[(h >> 48) % len(kinds)], "confidence": 0.5},
        "stale": {"noul": ((h >> 56) % 1000) / 1000},
        "toxic": {"noul": ((h >> 64) % 1000) / 10000},
        "relevant": {"noul": ((h >> 72) % 1000) / 1000},
        "event": {"choice": "no_event", "confidence": 0.5},
        "surprise": {"score": ((h >> 80) % 200) / 100, "confidence": 0.5},
        "durable": {"noul": ((h >> 88) % 1000) / 1000},
    }


async def _score_async(jobs: list[HeadlineJob], concurrency: int, model: str | None) -> list[dict]:
    from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeAPIError

    sem = asyncio.Semaphore(concurrency)
    out: list[dict] = []
    async with AsyncTypeSafeClient(
        model=model, retry=RetryPolicy(max_retries=3, backoff_max=8.0), timeout=20.0
    ) as client:

        async def one(job: HeadlineJob):
            async with sem:
                state = headline_state(job.symbol, job.headline, job.summary, job.source, job.symbols)
                try:
                    r = await client.system_one(state, HEADLINE_QUESTIONS)
                    row = {
                        "key": job.key,
                        "symbol": job.symbol,
                        "model": r.model,
                        "input_tokens": r.usage.input_tokens,
                        "questions_version": QUESTIONS_VERSION,
                        "error": None,
                        **flatten(r.answers),
                    }
                except TypeSafeAPIError as e:
                    row = {
                        "key": job.key,
                        "symbol": job.symbol,
                        "model": None,
                        "input_tokens": 0,
                        "questions_version": QUESTIONS_VERSION,
                        "error": f"{e.status}: {str(e)[:120]}",
                    }
                except Exception as e:  # noqa: BLE001
                    row = {
                        "key": job.key,
                        "symbol": job.symbol,
                        "model": None,
                        "input_tokens": 0,
                        "questions_version": QUESTIONS_VERSION,
                        "error": str(e)[:160],
                    }
                out.append(row)
                if len(out) % 500 == 0:
                    logger.info("scored {} / {}", len(out), len(jobs))

        await asyncio.gather(*(one(j) for j in jobs))
    return out


def score_headlines(
    jobs: Iterable[HeadlineJob], concurrency: int = 16, model: str | None = None, mock: bool = False
) -> list[dict]:
    jobs = list(jobs)
    if not jobs:
        return []
    if mock:
        return [
            {
                "key": j.key,
                "symbol": j.symbol,
                "model": "mock",
                "input_tokens": 0,
                "questions_version": QUESTIONS_VERSION,
                "error": None,
                **flatten(mock_answers(j)),
            }
            for j in jobs
        ]
    return asyncio.run(_score_async(jobs, concurrency, model))


def to_json(row: dict) -> str:
    return json.dumps(row, default=str)
