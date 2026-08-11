#!/usr/bin/env python3
"""Compile an intent-aware, bounded prompt from one task brief and manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from task_workflow import write_compiled_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    args = parser.parse_args()
    task_dir = args.task_dir.expanduser().resolve()
    if not (task_dir / "brief.json").is_file():
        raise SystemExit("--task-dir must contain brief.json")
    output = write_compiled_prompt(task_dir)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
