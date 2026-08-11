#!/usr/bin/env python3
"""Record one immutable generation attempt and optionally accept it."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from task_workflow import (
    ATTEMPT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    elapsed_seconds,
    latency_budget,
    parse_timestamp,
    read_json,
)
from workflow_common import atomic_write_json, now_iso


def parse_failure(value: str) -> dict[str, str]:
    category, separator, note = value.partition("=")
    if not separator or not category.strip() or not note.strip():
        raise argparse.ArgumentTypeError("failure must look like CATEGORY=NOTE")
    return {"category": category.strip(), "note": note.strip()}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument(
        "--status", choices=("accepted", "rejected", "error"), required=True
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--failure", type=parse_failure, action="append", default=[])
    parser.add_argument(
        "--reference-blame",
        action="append",
        default=[],
        help=(
            "Reference item ID directly implicated in a rejected attempt. "
            "Omit for generator, preservation, or prompt failures that should not "
            "lower reference ranking."
        ),
    )
    parser.add_argument("--feedback", default="")
    parser.add_argument("--preference-tag", action="append", default=[])
    parser.add_argument("--generator", default="built-in image_gen")
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument(
        "--response-started-at",
        help=(
            "ISO-8601 start of the current user-visible response. Defaults to "
            "response-window.json, or brief.created_at for the first attempt."
        ),
    )
    args = parser.parse_args()
    if args.duration_seconds is not None and args.duration_seconds < 0:
        raise SystemExit("--duration-seconds cannot be negative")

    task_dir = args.task_dir.expanduser().resolve()
    brief = read_json(task_dir / "brief.json")
    manifest = read_json(task_dir / "reference-manifest.json")
    output = args.output.expanduser().resolve() if args.output else None
    if args.status != "error" and (output is None or not output.is_file()):
        raise SystemExit("accepted/rejected attempts require an existing --output")
    if args.status == "rejected" and not args.failure:
        raise SystemExit("rejected attempts require at least one --failure")
    if args.status == "error" and not any(
        failure.get("category") == "technical" for failure in args.failure
    ):
        raise SystemExit(
            "error attempts require --failure technical=NOTE so retry limits work"
        )

    attempts_root = task_dir / "attempts"
    attempts_root.mkdir(exist_ok=True)
    existing = sorted(
        int(path.name)
        for path in attempts_root.iterdir()
        if path.is_dir() and path.name.isdigit()
    )
    number = (existing[-1] + 1) if existing else 1
    attempt_dir = attempts_root / f"{number:03d}"
    attempt_dir.mkdir()

    references = manifest.get("references", [])
    reference_item_ids = [entry.get("item_id") for entry in references]
    blame_item_ids = sorted(set(args.reference_blame))
    unknown_blame = sorted(set(blame_item_ids) - set(reference_item_ids))
    if unknown_blame:
        raise SystemExit(
            "--reference-blame must name a manifest item ID: "
            + ", ".join(unknown_blame)
        )
    if blame_item_ids and args.status != "rejected":
        raise SystemExit("--reference-blame is valid only for rejected attempts")
    recorded_at = now_iso()
    response_window_path = task_dir / "response-window.json"
    response_window = (
        read_json(response_window_path) if response_window_path.is_file() else {}
    )
    response_started_at = (
        args.response_started_at
        or response_window.get("started_at")
        or (brief.get("created_at") if number == 1 else None)
    )
    response_seconds = None
    if response_started_at:
        try:
            parse_timestamp(response_started_at)
            response_seconds = elapsed_seconds(response_started_at, recorded_at)
        except ValueError as exc:
            raise SystemExit(f"invalid response start timestamp: {exc}") from exc
    budget = latency_budget(brief)
    generation_started_at = response_window.get("generation_started_at")
    pre_generation_seconds = response_window.get("pre_generation_seconds")
    if pre_generation_seconds is None and response_started_at and generation_started_at:
        try:
            pre_generation_seconds = elapsed_seconds(
                response_started_at, generation_started_at
            )
        except ValueError as exc:
            raise SystemExit(f"invalid generation start timestamp: {exc}") from exc
    generation_seconds = args.duration_seconds
    post_generation_seconds = None
    if (
        response_seconds is not None
        and isinstance(pre_generation_seconds, (int, float))
        and generation_seconds is not None
    ):
        post_generation_seconds = round(
            max(0.0, response_seconds - pre_generation_seconds - generation_seconds),
            1,
        )
    workflow_overhead_seconds = None
    if isinstance(pre_generation_seconds, (int, float)):
        workflow_overhead_seconds = float(pre_generation_seconds)
        if post_generation_seconds is not None:
            workflow_overhead_seconds = round(
                workflow_overhead_seconds + post_generation_seconds, 1
            )
    pre_target = int(
        response_window.get("pre_generation_target_seconds")
        or budget["pre_generation_target_seconds"]
    )
    post_target = int(
        response_window.get("post_generation_target_seconds")
        or budget["post_generation_target_seconds"]
    )
    legacy_slo = response_window.get("response_slo_seconds")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA_VERSION,
        "attempt": number,
        "recorded_at": recorded_at,
        "status": args.status,
        "generator": args.generator,
        "duration_seconds": args.duration_seconds,
        "generation_seconds": generation_seconds,
        "response_started_at": response_started_at,
        "response_seconds": response_seconds,
        "pre_generation_seconds": pre_generation_seconds,
        "pre_generation_target_seconds": pre_target,
        "pre_generation_target_met": (
            pre_generation_seconds <= pre_target
            if isinstance(pre_generation_seconds, (int, float))
            else None
        ),
        "post_generation_seconds": post_generation_seconds,
        "post_generation_target_seconds": post_target,
        "post_generation_target_met": (
            post_generation_seconds <= post_target
            if post_generation_seconds is not None
            else None
        ),
        "workflow_overhead_seconds": workflow_overhead_seconds,
        "response_slo_seconds": legacy_slo,
        "response_slo_met": (
            response_seconds <= legacy_slo
            if response_seconds is not None and legacy_slo is not None
            else None
        ),
        "output": str(output) if output else None,
        "output_sha256": file_hash(output) if output else None,
        "reference_item_ids": reference_item_ids,
        "reference_blame_item_ids": blame_item_ids,
        "failures": args.failure,
        "user_feedback": args.feedback,
        "preference_tags": sorted(set(args.preference_tag)),
    }
    atomic_write_json(attempt_dir / "attempt.json", attempt)
    for name in ("prompt.md", "reference-manifest.json", "qa.json"):
        source = task_dir / name
        if source.is_file():
            shutil.copy2(source, attempt_dir / name)

    if response_window_path.is_file():
        response_window.update(
            {
                "phase": "recorded",
                "recorded_at": recorded_at,
                "last_attempt": number,
                "last_status": args.status,
            }
        )
        atomic_write_json(response_window_path, response_window)

    if args.feedback or args.preference_tag:
        event = {
            "schema_version": 1,
            "recorded_at": now_iso(),
            "attempt": number,
            "status": args.status,
            "feedback": args.feedback,
            "tags": sorted(set(args.preference_tag)),
        }
        with (task_dir / "preference-events.jsonl").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    if args.status == "accepted":
        attempt_rows = [
            read_json(path) for path in sorted(attempts_root.glob("*/attempt.json"))
        ]
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "status": "accepted",
            "generated_at": now_iso(),
            "generator": args.generator,
            "accepted_attempt": number,
            "revision_required": number > 1,
            "output": str(output),
            "medium": brief.get("medium"),
            "intent": brief.get("intent"),
            "response_seconds": response_seconds,
            "generation_seconds": generation_seconds,
            "pre_generation_seconds": pre_generation_seconds,
            "pre_generation_target_seconds": pre_target,
            "pre_generation_target_met": attempt["pre_generation_target_met"],
            "post_generation_seconds": post_generation_seconds,
            "post_generation_target_seconds": post_target,
            "post_generation_target_met": attempt["post_generation_target_met"],
            "workflow_overhead_seconds": workflow_overhead_seconds,
            "revisions": [
                {
                    "attempt": row.get("attempt"),
                    "status": row.get("status"),
                    "failures": row.get("failures", []),
                    "user_feedback": row.get("user_feedback", ""),
                }
                for row in attempt_rows
            ],
            "qa": "pass",
        }
        atomic_write_json(task_dir / "result.json", result)

    print(attempt_dir / "attempt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
