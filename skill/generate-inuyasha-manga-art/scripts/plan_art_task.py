#!/usr/bin/env python3
"""Initialize an art task and write the exact serial retrieval commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from init_art_task import parse_identity_form
from workflow_common import (
    FORM_VALUES,
    SHOT_VALUES,
    atomic_write_json,
    load_config,
    workflow_root,
)

SCRIPTS = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--medium", choices=("manga", "tv"), default="manga")
    parser.add_argument(
        "--deliverable",
        choices=("illustration", "manga-page", "character-sheet"),
        default="illustration",
    )
    parser.add_argument(
        "--identity-form", type=parse_identity_form, action="append", required=True
    )
    parser.add_argument("--shot", choices=SHOT_VALUES)
    parser.add_argument("--aspect-ratio", default="2:3 portrait")
    parser.add_argument(
        "--continuity",
        action="store_true",
        help="Inspect selected-output only when accepted visual continuity is required.",
    )
    parser.add_argument(
        "--content-query",
        default="",
        help="One exact catalog term for content evidence and cross-medium fallback.",
    )
    parser.add_argument(
        "--content-focus",
        default="",
        help="Exact visible content the selected content reference may control.",
    )
    parser.add_argument(
        "--content-provenance",
        choices=("observed-content", "fallback-medium-original"),
        default="observed-content",
        help="Label content that is genuinely original to the fallback medium.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=3,
        help="Maximum candidates shown per retrieval layer (default: 3; hard max: 6).",
    )
    args = parser.parse_args()
    if args.candidate_limit < 1 or args.candidate_limit > 6:
        raise SystemExit("--candidate-limit must be between 1 and 6")
    args.content_query = args.content_query.strip()
    args.content_focus = args.content_focus.strip()
    if bool(args.content_query) != bool(args.content_focus):
        raise SystemExit(
            "--content-query and --content-focus must be supplied together"
        )
    if not args.content_query and args.content_provenance != "observed-content":
        raise SystemExit("--content-provenance requires a planned content query")
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    check = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "build_reference_index.py"),
            "--workflow-root",
            str(root),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode == 3:
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "build_reference_index.py"),
                "--workflow-root",
                str(root),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    elif check.returncode != 0:
        raise SystemExit(check.stderr.strip() or check.stdout.strip())
    command = [
        sys.executable,
        str(SCRIPTS / "init_art_task.py"),
        "--workflow-root",
        str(root),
        "--slug",
        args.slug,
        "--medium",
        args.medium,
        "--deliverable",
        args.deliverable,
        "--request",
        args.request,
        "--intent",
        "new",
        "--aspect-ratio",
        args.aspect_ratio,
    ]
    for character, form in args.identity_form:
        if form not in FORM_VALUES:
            raise SystemExit(f"Unsupported form: {form}")
        command.extend(["--identity-form", f"{character}={form}"])
    if args.content_query:
        command.extend(["--content-query", args.content_query])
        command.extend(["--content-focus", args.content_focus])
        command.extend(["--content-provenance", args.content_provenance])
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    task_dir = Path(completed.stdout.strip().splitlines()[-1]).resolve()

    # Record the interpreter already running the planner. This keeps generated
    # command arrays directly executable on macOS, Linux, and Windows.
    launcher = sys.executable
    official_commands = []
    official_fallback_commands = []
    for character, form in args.identity_form:
        fallback = [
            launcher,
            str(SCRIPTS / "search_reference_index.py"),
            "--source",
            "official",
            "--subject",
            character,
            "--form",
            form,
            "--limit",
            str(args.candidate_limit),
        ]
        parts = list(fallback)
        if args.shot:
            parts.extend(["--shot", args.shot])
        official_commands.append(parts)
        if args.shot:
            official_fallback_commands.append(fallback)
    focal_character, focal_form = args.identity_form[0]
    style_source = "manga-curated" if args.medium == "manga" else "tv-curated"
    fallback_common = ["--subject", focal_character, "--form", focal_form]
    common = list(fallback_common)
    if args.shot:
        common.extend(["--shot", args.shot])
    style_primary = [
        launcher,
        str(SCRIPTS / "browse_curated_styles.py"),
        "--source",
        style_source,
        *common,
        "--limit",
        str(args.candidate_limit),
        "--columns",
        "3",
    ]
    style_fallback = [
        launcher,
        str(SCRIPTS / "browse_curated_styles.py"),
        "--source",
        style_source,
        *fallback_common,
        "--limit",
        str(args.candidate_limit),
        "--columns",
        "3",
    ]
    layers = [
        {
            "layer": 1,
            "source": "official",
            "primary_commands": official_commands,
            "fallback_without_shot": official_fallback_commands,
            "selection_budget": "one identity sheet per focal character; add a focused crop only for an unresolved construction detail",
        },
        {
            "layer": 2,
            "source": style_source,
            "primary_commands": [style_primary],
            "fallback_without_shot": [style_fallback] if args.shot else [],
            "selection_budget": "one style screenshot by default; two only when one cannot resolve the requested rendering grammar",
        },
    ]
    if args.content_query:
        fallback_content_source = (
            "tv-curated" if args.medium == "manga" else "manga-curated"
        )

        def content_command(source: str, include_shot: bool) -> list[str]:
            parts = [
                launcher,
                str(SCRIPTS / "browse_curated_styles.py"),
                "--source",
                source,
                "--exact-term",
                args.content_query,
            ]
            if include_shot and args.shot:
                parts.extend(["--shot", args.shot])
            parts.extend(["--limit", str(args.candidate_limit), "--columns", "3"])
            return parts

        layers.append(
            {
                "layer": 3,
                "role": "content",
                "need": args.content_focus,
                "selected_medium": {
                    "source": style_source,
                    "primary_commands": [content_command(style_source, True)],
                    "fallback_without_shot": (
                        [content_command(style_source, False)] if args.shot else []
                    ),
                },
                "cross_medium_fallback": {
                    "source": fallback_content_source,
                    "allowed_after": ["MISS", "INSUFFICIENT"],
                    "primary_commands": [
                        content_command(fallback_content_source, True)
                    ],
                    "fallback_without_shot": (
                        [content_command(fallback_content_source, False)]
                        if args.shot
                        else []
                    ),
                },
                "selection_budget": (
                    "at most one exact-focus content image; a cross-medium hit is "
                    "content evidence only and never style or identity evidence"
                ),
            }
        )
    if args.continuity:
        continuity_primary = [
            launcher,
            str(SCRIPTS / "browse_curated_styles.py"),
            "--source",
            "selected-output",
            *common,
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "3",
        ]
        continuity_fallback = [
            launcher,
            str(SCRIPTS / "browse_curated_styles.py"),
            "--source",
            "selected-output",
            *fallback_common,
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "3",
        ]
        layers.append(
            {
                "layer": len(layers) + 1,
                "source": "selected-output",
                "primary_commands": [continuity_primary],
                "fallback_without_shot": [continuity_fallback] if args.shot else [],
                "selection_budget": "at most one explicitly requested continuity precedent",
            }
        )

    plan = {
        "schema_version": 3,
        "task": task_dir.name,
        "gate": "Run one layer, inspect candidates, record HIT/MISS/INSUFFICIENT, then advance.",
        "mode": (
            "cross-medium-content"
            if args.content_query
            else ("continuity" if args.continuity else "fast-default")
        ),
        "candidate_limit": args.candidate_limit,
        "timing_policy": {
            "pre_generation_target_seconds": 90,
            "post_generation_target_seconds": 30,
            "generation_latency": "observe-only",
        },
        "execution_boundaries": [
            "one serial candidate inspection",
            "one batched prepare-compile-validate step",
            "one image-generation call",
            "one blocking check and preview handoff",
        ],
        "continuity_requested": args.continuity,
        "content_need": (
            {
                "query": args.content_query,
                "focus": args.content_focus,
                "provenance": args.content_provenance,
            }
            if args.content_query
            else None
        ),
        "layers": layers,
    }
    brief_path = task_dir / "brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    if args.content_query:
        brief["style_strategy"] = f"{args.medium}-style-cross-medium-content"
    else:
        brief["style_strategy"] = (
            f"three-layer-{args.medium}-continuity"
            if args.continuity
            else f"two-layer-{args.medium}-fast"
        )
    atomic_write_json(brief_path, brief)
    atomic_write_json(task_dir / "retrieval-plan.json", plan)
    print(
        json.dumps(
            {
                "task_dir": str(task_dir),
                "retrieval_plan": str(task_dir / "retrieval-plan.json"),
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
        print(exc.stderr.strip() or exc.stdout.strip() or str(exc), file=sys.stderr)
        raise SystemExit(2)
