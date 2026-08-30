#!/usr/bin/env python3
"""Compile an intent-aware, bounded prompt from one task brief and manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_workflow import (
    compile_prompt_artifacts,
    read_prompt_compile_inputs,
    write_compiled_prompt,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print the compilation plan without changing prompt.md or its report.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    task_dir = args.task_dir.expanduser().resolve()
    if not (task_dir / "brief.json").is_file():
        raise SystemExit("--task-dir must contain brief.json")
    if args.explain:
        _, report = compile_prompt_artifacts(*read_prompt_compile_inputs(task_dir))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    output = write_compiled_prompt(task_dir)
    if args.json:
        print(
            json.dumps(
                {
                    "prompt": str(output),
                    "report": str(task_dir / "prompt-compile.json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
