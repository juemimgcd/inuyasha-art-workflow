#!/usr/bin/env python3
"""Quarantine an invalid historical art task without rewriting its evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_common import (
    atomic_write_json,
    load_config,
    now_iso,
    workflow_paths,
    workflow_root,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--reason", default="")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    config = load_config()
    root = workflow_root(config, args.workflow_root)
    tasks_root = workflow_paths(root)["tasks"].resolve()
    task_dir = args.task_dir.expanduser().resolve()
    if task_dir.parent != tasks_root or not task_dir.is_dir():
        raise SystemExit("--task-dir must be directly under the workflow tasks directory")

    archive_path = task_dir / "archived.json"
    if args.restore:
        if not archive_path.is_file():
            raise SystemExit("Task is not archived")
        archive_path.unlink()
        print(f"RESTORED {task_dir.name}")
        return 0

    if archive_path.is_file():
        archive = json.loads(archive_path.read_text(encoding="utf-8"))
        print(f"ARCHIVED {task_dir.name}: {archive.get('reason', '')}")
        return 0
    if not args.reason.strip():
        raise SystemExit("--reason is required when archiving a task")

    result_path = task_dir / "result.json"
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {}
    )
    record = {
        "schema_version": 1,
        "task_id": task_dir.name,
        "archived_at": now_iso(),
        "reason": args.reason.strip(),
        "previous_result_status": result.get("status"),
        "previous_output": result.get("output")
        or result.get("task_output")
        or result.get("accepted_output"),
        "reversible": True,
    }
    if not args.apply:
        print(json.dumps({"action": "archive", **record}, ensure_ascii=False, indent=2))
        return 0

    atomic_write_json(archive_path, record)
    print(f"ARCHIVED {task_dir.name}: {record['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
