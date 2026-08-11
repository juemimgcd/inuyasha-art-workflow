#!/usr/bin/env python3
"""Plan or apply conservative schema upgrades for legacy completed art tasks."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

from task_workflow import (
    ATTEMPT_SCHEMA_VERSION,
    BRIEF_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    read_json,
    result_output,
    task_intent,
)
from workflow_common import (
    atomic_write_json,
    load_config,
    now_iso,
    workflow_paths,
    workflow_root,
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate(task_dir: Path, apply: bool) -> list[str]:
    if (task_dir / "archived.json").is_file():
        return ["archived"]
    actions = []
    brief_path = task_dir / "brief.json"
    if not brief_path.is_file():
        return ["missing brief.json"]
    brief = read_json(brief_path)
    if brief.get("schema_version", 0) < BRIEF_SCHEMA_VERSION:
        actions.append(f"brief schema -> {BRIEF_SCHEMA_VERSION}")
        if apply:
            brief.update(
                {
                    "schema_version": BRIEF_SCHEMA_VERSION,
                    "intent": task_intent(brief),
                    "parent_task_id": brief.get("parent_task_id"),
                    "change_category": brief.get("change_category"),
                    "change_request": brief.get("change_request", ""),
                }
            )
            atomic_write_json(brief_path, brief)

    result_path = task_dir / "result.json"
    if not result_path.is_file():
        if actions:
            actions.append("incomplete task; no result migration")
            return actions
        return ["current incomplete"]
    result = read_json(result_path)
    if result.get("schema_version") == RESULT_SCHEMA_VERSION and isinstance(
        result.get("accepted_attempt"), int
    ):
        return actions or ["current"]
    output = result_output(result)
    if output is None or not output.is_file():
        actions.append("cannot migrate result: accepted output missing")
        return actions
    actions.append(
        f"import legacy acceptance as attempt 001 and result schema {RESULT_SCHEMA_VERSION}"
    )
    if not apply:
        return actions

    manifest = read_json(task_dir / "reference-manifest.json")
    attempt_dir = task_dir / "attempts" / "001"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    attempt = {
        "schema_version": ATTEMPT_SCHEMA_VERSION,
        "attempt": 1,
        "recorded_at": result.get("generated_at") or now_iso(),
        "status": "accepted",
        "generator": result.get("generator", "legacy import"),
        "duration_seconds": None,
        "output": str(output),
        "output_sha256": file_hash(output),
        "reference_item_ids": [
            entry.get("item_id") for entry in manifest.get("references", [])
        ],
        "failures": [],
        "user_feedback": "",
        "preference_tags": [],
        "legacy_import": True,
    }
    atomic_write_json(attempt_dir / "attempt.json", attempt)
    for name in ("prompt.md", "reference-manifest.json", "qa.json"):
        source = task_dir / name
        if source.is_file():
            shutil.copy2(source, attempt_dir / name)
    normalized = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "accepted",
        "generated_at": result.get("generated_at") or now_iso(),
        "generator": result.get("generator", "legacy import"),
        "accepted_attempt": 1,
        "revision_required": bool(result.get("revision_required")),
        "output": str(output),
        "medium": brief.get("medium"),
        "intent": task_intent(brief),
        "revisions": [
            {
                "attempt": 1,
                "status": "accepted",
                "failures": [],
                "user_feedback": "legacy import; detailed rejected attempts unavailable",
            }
        ],
        "qa": result.get("qa", "pass"),
        "legacy_import": True,
    }
    if result.get("reference_audit_warning"):
        normalized["reference_audit_warning"] = result["reference_audit_warning"]
    atomic_write_json(result_path, normalized)
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--task-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    tasks_root = workflow_paths(root)["tasks"].resolve()
    if args.task_dir:
        task_dirs = [args.task_dir.expanduser().resolve()]
        if task_dirs[0].parent != tasks_root:
            raise SystemExit(
                "--task-dir must be directly under the workflow tasks directory"
            )
    else:
        task_dirs = sorted(path for path in tasks_root.iterdir() if path.is_dir())
    changed = 0
    for task_dir in task_dirs:
        actions = migrate(task_dir, args.apply)
        if actions not in (["current"], ["current incomplete"], ["archived"]):
            changed += 1
        mode = "APPLY" if args.apply else "PLAN"
        print(f"{mode} {task_dir.name}: {'; '.join(actions)}")
    print(f"Tasks requiring attention: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
