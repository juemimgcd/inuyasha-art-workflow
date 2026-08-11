#!/usr/bin/env python3
"""Validate all completed art tasks and report schema or reference drift."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from workflow_common import load_config, workflow_paths, workflow_root

SCRIPTS = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--include-incomplete", action="store_true")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    tasks_root = workflow_paths(root)["tasks"]
    results = []
    archived_tasks = []
    for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        archived_path = task_dir / "archived.json"
        if archived_path.is_file() and not args.include_archived:
            try:
                archived = json.loads(archived_path.read_text(encoding="utf-8"))
                reason = archived.get("reason", "")
            except (OSError, json.JSONDecodeError):
                reason = "unreadable archive record"
            archived_tasks.append({"task": task_dir.name, "reason": reason})
            continue
        completed = (task_dir / "result.json").is_file()
        if not completed and not args.include_incomplete:
            continue
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
        results.append({"task": task_dir.name, "stage": stage, **payload})
    summary = {
        "ok": all(row.get("ok") for row in results),
        "validated": len(results),
        "passed": sum(bool(row.get("ok")) for row in results),
        "failed": sum(not row.get("ok") for row in results),
        "archived": len(archived_tasks),
        "archived_tasks": archived_tasks,
        "tasks": results,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"Validated {summary['validated']} tasks: "
            f"passed={summary['passed']} failed={summary['failed']} "
            f"archived={summary['archived']}"
        )
        for row in archived_tasks:
            print(f"ARCHIVED {row['task']}: {row['reason']}")
        for row in results:
            status = "PASS" if row.get("ok") else "FAIL"
            print(f"{status} {row['task']} ({row['stage']})")
            for failure in row.get("failures", []):
                print(f"  - {failure}")
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
