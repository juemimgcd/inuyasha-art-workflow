#!/usr/bin/env python3
"""Start phase timing or mark image generation for an existing art task."""

from __future__ import annotations

import argparse
from pathlib import Path

from task_workflow import (
    LATENCY_SCHEMA_VERSION,
    elapsed_seconds,
    latency_budget,
    read_json,
)
from workflow_common import atomic_write_json, now_iso


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--pre-generation-target-seconds", type=int)
    parser.add_argument("--post-generation-target-seconds", type=int)
    parser.add_argument(
        "--mark-generation-started",
        action="store_true",
        help="Mark the end of controllable preparation without resetting the window.",
    )
    parser.add_argument(
        "--response-slo-seconds",
        type=int,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    task_dir = args.task_dir.expanduser().resolve()
    brief = read_json(task_dir / "brief.json")
    configured = latency_budget(brief)
    path = task_dir / "response-window.json"
    if args.mark_generation_started:
        window = read_json(path) if path.is_file() else {}
        started_at = window.get("pre_generation_started_at") or window.get(
            "started_at"
        )
        if not started_at:
            started_at = now_iso()
        generation_started_at = now_iso()
        window.update(
            {
                "schema_version": LATENCY_SCHEMA_VERSION,
                "started_at": started_at,
                "pre_generation_started_at": started_at,
                "generation_started_at": generation_started_at,
                "pre_generation_seconds": elapsed_seconds(
                    started_at, generation_started_at
                ),
                "pre_generation_target_seconds": configured[
                    "pre_generation_target_seconds"
                ],
                "post_generation_target_seconds": configured[
                    "post_generation_target_seconds"
                ],
                "phase": "generation",
            }
        )
        atomic_write_json(path, window)
        print(path)
        return 0

    pre_target = (
        args.pre_generation_target_seconds
        or configured["pre_generation_target_seconds"]
    )
    post_target = (
        args.post_generation_target_seconds
        or configured["post_generation_target_seconds"]
    )
    if pre_target < 1 or post_target < 1:
        raise SystemExit("phase targets must be positive integers")
    started_at = now_iso()
    window = {
        "schema_version": LATENCY_SCHEMA_VERSION,
        "started_at": started_at,
        "pre_generation_started_at": started_at,
        "pre_generation_target_seconds": pre_target,
        "post_generation_target_seconds": post_target,
        "generation_latency_policy": "observe-only",
        "phase": "pre-generation",
    }
    atomic_write_json(path, window)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
