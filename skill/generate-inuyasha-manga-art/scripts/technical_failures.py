#!/usr/bin/env python3
"""Classify recorded technical failures for retry gating and reporting."""

from __future__ import annotations

from pathlib import Path

from task_workflow import read_json

NETWORK_RETRY_EXHAUSTED_SECONDS = 180.0
NETWORK_MARKERS = (
    "network error",
    "error sending request",
    "/codex/images/edits",
    "images/edits",
)


def is_network_failure(attempt: dict) -> bool:
    if attempt.get("status") != "error":
        return False
    notes = " ".join(
        str(failure.get("note", ""))
        for failure in attempt.get("failures", [])
        if isinstance(failure, dict) and failure.get("category") == "technical"
    ).lower()
    return any(marker in notes for marker in NETWORK_MARKERS)


def transport_retry_exhausted(attempt: dict) -> bool:
    explicit = attempt.get("transport_retry_exhausted")
    if isinstance(explicit, bool):
        return explicit
    duration = attempt.get("generation_seconds", attempt.get("duration_seconds"))
    return (
        is_network_failure(attempt)
        and isinstance(duration, (int, float))
        and float(duration) >= NETWORK_RETRY_EXHAUSTED_SECONDS
    )


def latest_attempt(task_dir: Path) -> tuple[Path, dict] | None:
    paths = sorted((task_dir / "attempts").glob("*/attempt.json"))
    if not paths:
        return None
    path = paths[-1]
    return path, read_json(path)


def unresolved_exhausted_network_failure(
    task_dir: Path,
) -> tuple[Path, dict] | None:
    latest = latest_attempt(task_dir)
    if latest is None or not transport_retry_exhausted(latest[1]):
        return None
    return latest
