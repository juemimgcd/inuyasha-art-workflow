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
from technical_failures import unresolved_exhausted_network_failure
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
        "--authorize-network-retry",
        action="store_true",
        help=(
            "Open one user-authorized retry after a long network failure already "
            "exhausted the image client's internal retries."
        ),
    )
    parser.add_argument(
        "--authorization-note",
        help="Required audit note describing the user's explicit retry request.",
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
        submission_path = task_dir / "generation-submission.json"
        submission = read_json(submission_path) if submission_path.is_file() else None
        if int(brief.get("schema_version") or 0) >= 5:
            if submission is None:
                raise SystemExit(
                    "prepare_generation_submission.py must snapshot the exact call "
                    "before generation starts"
                )
            from prepare_generation_submission import validate_generation_submission

            submission_failures = validate_generation_submission(task_dir, submission)
            if submission_failures:
                raise SystemExit("; ".join(submission_failures))
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
        if submission is not None:
            submission.update(
                {"state": "submitted", "generation_started_at": generation_started_at}
            )
            atomic_write_json(submission_path, submission)
        print(path)
        return 0

    if args.authorization_note and not args.authorize_network_retry:
        raise SystemExit("--authorization-note requires --authorize-network-retry")
    unresolved = unresolved_exhausted_network_failure(task_dir)
    if unresolved is not None and not args.authorize_network_retry:
        attempt_path, _ = unresolved
        raise SystemExit(
            "network retry stop: the latest image call already exhausted the "
            "client's internal transport retries; do not start another call unless "
            "the user explicitly requests it, then pass --authorize-network-retry "
            f"and --authorization-note (blocked by {attempt_path})"
        )
    if args.authorize_network_retry:
        if unresolved is None:
            raise SystemExit(
                "--authorize-network-retry is valid only after an unresolved "
                "transport-exhausted network failure"
            )
        if not args.authorization_note or not args.authorization_note.strip():
            raise SystemExit(
                "--authorize-network-retry requires a non-empty --authorization-note"
            )

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
    if unresolved is not None:
        attempt_path, attempt = unresolved
        window.update(
            {
                "network_retry_authorized": True,
                "network_retry_authorized_attempt": attempt.get("attempt"),
                "network_retry_authorization_note": args.authorization_note.strip(),
                "network_retry_blocking_attempt_path": str(attempt_path),
            }
        )
    atomic_write_json(path, window)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
