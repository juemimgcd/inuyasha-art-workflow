#!/usr/bin/env python3
"""Build a conservative medium-specific preference profile from explicit feedback."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from task_workflow import read_json
from workflow_common import (
    atomic_write_json,
    load_config,
    now_iso,
    workflow_paths,
    workflow_root,
)


def build_profile(root: Path, minimum_support: int = 2) -> dict:
    """Aggregate only explicit accepted feedback into a reusable profile."""
    if minimum_support < 1:
        raise ValueError("minimum_support must be positive")
    tasks_root = workflow_paths(root)["tasks"]
    counts = {"manga": Counter(), "tv": Counter()}
    feedback = {"manga": [], "tv": []}
    task_dirs = tasks_root.iterdir() if tasks_root.is_dir() else ()
    for task_dir in task_dirs:
        if (task_dir / "archived.json").is_file():
            continue
        brief_path = task_dir / "brief.json"
        events_path = task_dir / "preference-events.jsonl"
        if not brief_path.is_file() or not events_path.is_file():
            continue
        brief = read_json(brief_path)
        medium = brief.get("medium")
        if medium not in counts:
            continue
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("status") != "accepted":
                continue
            counts[medium].update(event.get("tags", []))
            if event.get("feedback"):
                feedback[medium].append(event["feedback"])

    profile = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "minimum_support": minimum_support,
    }
    for medium in ("manga", "tv"):
        profile[medium] = {
            "traits": [
                {"tag": tag, "count": count}
                for tag, count in counts[medium].most_common()
            ],
            "recent_feedback": feedback[medium][-20:],
        }
    return profile


def write_profile(root: Path, minimum_support: int = 2) -> Path:
    """Refresh the workflow-level profile after an accepted feedback event."""
    output = root / "preference-profile.json"
    atomic_write_json(output, build_profile(root, minimum_support))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--minimum-support", type=int, default=2)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.minimum_support < 1:
        raise SystemExit("--minimum-support must be positive")

    config = load_config()
    root = workflow_root(config, args.workflow_root)
    profile = build_profile(root, args.minimum_support)
    if args.write:
        output = write_profile(root, args.minimum_support)
        print(output)
    else:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
