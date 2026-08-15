#!/usr/bin/env python3
"""Prepare a target-only tracked edit and exact generation submission in one call."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from task_workflow import CHANGE_CATEGORIES, read_json
from workflow_common import SHOT_VALUES, atomic_write_json, atomic_write_text

SCRIPTS = Path(__file__).resolve().parent


def run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--change-category", choices=CHANGE_CATEGORIES, required=True)
    parser.add_argument("--medium", choices=("manga", "tv"), default="manga")
    parser.add_argument("--aspect-ratio", default="source target")
    parser.add_argument("--shot", choices=SHOT_VALUES)
    parser.add_argument(
        "--target-max-edge",
        type=int,
        help="Create a manifest-tracked JPEG transport proxy with this maximum edge.",
    )
    args = parser.parse_args()
    target = args.target.expanduser().resolve()
    if not target.is_file():
        raise SystemExit(f"target is missing: {target}")
    if args.target_max_edge is not None and args.target_max_edge < 256:
        raise SystemExit("--target-max-edge must be at least 256")

    init_command = [
        sys.executable,
        str(SCRIPTS / "init_art_task.py"),
        "--slug",
        args.slug,
        "--medium",
        args.medium,
        "--deliverable",
        "edit",
        "--intent",
        "edit",
        "--request",
        args.request,
        "--change-category",
        args.change_category,
        "--change-request",
        args.request,
        "--aspect-ratio",
        args.aspect_ratio,
    ]
    if args.workflow_root:
        init_command.extend(["--workflow-root", str(args.workflow_root.resolve())])
    if args.shot:
        init_command.extend(["--shot", args.shot])
    task_dir = Path(run(init_command).splitlines()[-1]).resolve()
    brief_path = task_dir / "brief.json"
    brief = read_json(brief_path)
    brief["scene"] = "Preserve the supplied target scene except for the named change."
    brief["invariants"] = [
        "Preserve target framing, composition, character placement, and unchanged content.",
        f"Change only {args.change_category}: {args.request}",
    ]
    atomic_write_json(brief_path, brief)
    atomic_write_text(
        task_dir / "evidence-log.md",
        f"""# Evidence log

Task: `{task_dir.name}`
Intent: `edit`

## Target evidence

- Source: user-supplied target
- Requested change: {args.request}
- Result: `HIT`; the target controls all unchanged identity, composition, medium, and scene facts.

## Additional evidence

- Result: `SKIP`; target-only first preview requires no unrelated retrieval.
""",
    )

    prepare_command = [
        sys.executable,
        str(SCRIPTS / "prepare_reference_set.py"),
        "--task-dir",
        str(task_dir),
        "--external",
        f"target={target}",
    ]
    if args.workflow_root:
        prepare_command.extend(["--workflow-root", str(args.workflow_root.resolve())])
    if args.target_max_edge is not None:
        prepare_command.extend(
            ["--external-target-max-edge", str(args.target_max_edge)]
        )
    run(prepare_command)
    run(
        [
            sys.executable,
            str(SCRIPTS / "compile_prompt.py"),
            "--task-dir",
            str(task_dir),
        ]
    )
    run(
        [
            sys.executable,
            str(SCRIPTS / "prepare_generation_submission.py"),
            "--task-dir",
            str(task_dir),
        ]
    )
    validate_command = [
        sys.executable,
        str(SCRIPTS / "validate_art_task.py"),
        "--task-dir",
        str(task_dir),
        "--stage",
        "pre-generation",
    ]
    if args.workflow_root:
        validate_command.extend(["--workflow-root", str(args.workflow_root.resolve())])
    validation = json.loads(run(validate_command))
    if not validation.get("ok"):
        raise SystemExit("quick edit validation failed")
    submission = json.loads(
        (task_dir / "generation-submission.json").read_text(encoding="utf-8")
    )
    print(
        json.dumps(
            {
                "task_dir": str(task_dir),
                "prompt": str(task_dir / "prompt.md"),
                "generation_submission": str(
                    task_dir / "generation-submission.json"
                ),
                "input_bytes": submission.get("input_bytes"),
                "ready_for_generation": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        print(message, file=sys.stderr)
        raise SystemExit(2)
