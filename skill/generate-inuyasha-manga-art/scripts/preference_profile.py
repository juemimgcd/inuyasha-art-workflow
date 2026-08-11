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
    tasks_root = workflow_paths(root)["tasks"]
    counts = {"manga": Counter(), "tv": Counter()}
    feedback = {"manga": [], "tv": []}
    for task_dir in tasks_root.iterdir():
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
        "minimum_support": args.minimum_support,
    }
    for medium in ("manga", "tv"):
        profile[medium] = {
            "traits": [
                {"tag": tag, "count": count}
                for tag, count in counts[medium].most_common()
            ],
            "recent_feedback": feedback[medium][-20:],
        }
    if args.write:
        output = root / "preference-profile.json"
        atomic_write_json(output, profile)
        print(output)
    else:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
