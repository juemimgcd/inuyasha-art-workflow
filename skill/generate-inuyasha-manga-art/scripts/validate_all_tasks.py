#!/usr/bin/env python3
"""Validate art tasks within an explicit lifecycle scope."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from workflow_common import load_config, workflow_paths, workflow_root

SCRIPTS = Path(__file__).resolve().parent
ACTIVE_LIFECYCLE_STATES = {"candidate-pending", "prepared"}


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def task_lifecycle_state(task_dir: Path) -> str:
    """Classify one task without rewriting append-only attempt history."""
    if (task_dir / "archived.json").is_file():
        return "archived"
    if (task_dir / "result.json").is_file():
        return "completed"
    attempts = sorted((task_dir / "attempts").glob("*/attempt.json"))
    if attempts:
        status = _read_json(attempts[-1]).get("status")
        if status == "candidate":
            return "candidate-pending"
        if status == "accepted":
            return "accepted-without-result"
        if status == "rejected":
            return "rejected-closed"
        if status == "error":
            return "error-blocked"
    submission = _read_json(task_dir / "generation-submission.json")
    response_window = _read_json(task_dir / "response-window.json")
    if submission.get("state") in {"prepared", "submitted"} or response_window.get(
        "phase"
    ) in {"prepared", "generation"}:
        return "prepared"
    return "draft"


def lifecycle_in_scope(state: str, scope: str) -> bool:
    if scope == "completed":
        return state == "completed"
    if scope == "active":
        return state in ACTIVE_LIFECYCLE_STATES
    return state != "archived"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument(
        "--scope",
        choices=("completed", "active", "all"),
        default="completed",
        help=(
            "completed validates accepted results; active validates only prepared "
            "or candidate-pending work; all includes closed and draft history"
        ),
    )
    parser.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Deprecated compatibility alias for --scope all.",
    )
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    scope = "all" if args.include_incomplete else args.scope
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    tasks_root = workflow_paths(root)["tasks"]
    results = []
    archived_tasks = []
    lifecycle_counts: dict[str, int] = {}
    for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        lifecycle = task_lifecycle_state(task_dir)
        lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1
        archived_path = task_dir / "archived.json"
        if archived_path.is_file() and not args.include_archived:
            try:
                archived = json.loads(archived_path.read_text(encoding="utf-8"))
                reason = archived.get("reason", "")
            except (OSError, json.JSONDecodeError):
                reason = "unreadable archive record"
            archived_tasks.append({"task": task_dir.name, "reason": reason})
            continue
        if lifecycle == "archived" and args.include_archived:
            selected = scope == "all" or (
                scope == "completed" and (task_dir / "result.json").is_file()
            )
        else:
            selected = lifecycle_in_scope(lifecycle, scope)
        if not selected:
            continue
        completed = (task_dir / "result.json").is_file()
        stage = "final" if completed else "pre-generation"
        command = [
            sys.executable,
            str(SCRIPTS / "validate_art_task.py"),
            "--workflow-root",
            str(root),
            "--task-dir",
            str(task_dir),
            "--stage",
            stage,
        ]
        completed_process = subprocess.run(
            command, capture_output=True, text=True, check=False
        )
        try:
            payload = json.loads(completed_process.stdout)
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "failures": [
                    completed_process.stderr.strip() or completed_process.stdout.strip()
                ],
            }
        results.append(
            {
                "task": task_dir.name,
                "lifecycle": lifecycle,
                "stage": stage,
                **payload,
            }
        )
    summary = {
        "ok": all(row.get("ok") for row in results),
        "scope": scope,
        "validated": len(results),
        "passed": sum(bool(row.get("ok")) for row in results),
        "failed": sum(not row.get("ok") for row in results),
        "archived": len(archived_tasks),
        "archived_tasks": archived_tasks,
        "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
        "tasks": results,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"Validated {summary['validated']} {scope} tasks: "
            f"passed={summary['passed']} failed={summary['failed']} "
            f"archived={summary['archived']}"
        )
        for row in archived_tasks:
            print(f"ARCHIVED {row['task']}: {row['reason']}")
        for row in results:
            status = "PASS" if row.get("ok") else "FAIL"
            print(
                f"{status} {row['task']} "
                f"({row['lifecycle']}; {row['stage']})"
            )
            for failure in row.get("failures", []):
                print(f"  - {failure}")
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
