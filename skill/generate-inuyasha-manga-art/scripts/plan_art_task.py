#!/usr/bin/env python3
"""Initialize an art task and write the exact serial retrieval commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from init_art_task import parse_identity_form
from task_workflow import IDENTITY_LEDGERS_PATH, build_rendering_map, read_json
from workflow_common import (
    FORM_VALUES,
    SHOT_VALUES,
    VIEW_ANGLE_VALUES,
    atomic_write_json,
    infer_canonical_scene,
    load_config,
    retrieval_traits_for,
    workflow_root,
)

SCRIPTS = Path(__file__).resolve().parent


def infer_prop_forms(request: str) -> list[tuple[str, str]]:
    """Infer named prop forms from ledger-owned aliases, without prop branches."""
    if not IDENTITY_LEDGERS_PATH.is_file():
        return []
    profiles = read_json(IDENTITY_LEDGERS_PATH).get("characters", {})
    inferred: list[tuple[str, str]] = []
    for prop, profile in profiles.items():
        inference = profile.get("form_inference") or {}
        if profile.get("kind") != "prop" or prop not in request or not inference:
            continue
        matches_by_strength: dict[str, list[str]] = {"explicit": [], "context": []}
        for form, rules in inference.items():
            if isinstance(rules, list):
                rule_groups = {"context": rules}
            else:
                rule_groups = rules
            for strength, matched_forms in matches_by_strength.items():
                aliases = rule_groups.get(strength, [])
                if any(str(alias) in request for alias in aliases):
                    matched_forms.append(form)
        resolved_form = None
        for matches in matches_by_strength.values():
            if len(matches) == 1:
                resolved_form = matches[0]
                break
            if len(matches) > 1:
                break
        if resolved_form is not None:
            inferred.append((prop, resolved_form))
            continue
        choices = ", ".join(inference)
        raise SystemExit(
            f"The request names {prop} but its canonical form is ambiguous; "
            f"pass --prop-form {prop}=FORM using one of: {choices}"
        )
    return inferred


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
    parser.add_argument(
        "--prop-form",
        type=parse_identity_form,
        action="append",
        default=[],
        help="Declare a canonical weapon or prop form.",
    )
    parser.add_argument(
        "--scene-material",
        action="append",
        default=[],
        help="Name scene-material scope that inherits the primary style anchor's economy.",
    )
    parser.add_argument("--shot", choices=SHOT_VALUES)
    parser.add_argument(
        "--view-angle",
        choices=VIEW_ANGLE_VALUES,
        help=(
            "Character view direction, stored separately from camera distance. "
            "When omitted, one unambiguous explicit request cue is inferred."
        ),
    )
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
        default=4,
        help="Maximum candidates shown per retrieval layer (default: 4; hard max: 6).",
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
    canonical_scene = infer_canonical_scene(args.request)
    scene_query = f"scene-id:{canonical_scene['id']}" if canonical_scene else ""
    scene_focus = (
        f"{canonical_scene['label']}的规范结构、比例、固定空间关系与漫画场景画法"
        if canonical_scene
        else ""
    )
    if canonical_scene and args.content_query:
        raise SystemExit(
            "A canonical scene already owns the one exact-content slot; create a "
            "separate follow-up task for another exact-content lookup"
        )
    prop_forms = args.prop_form or infer_prop_forms(args.request)
    if len(dict(prop_forms)) != len(prop_forms):
        raise SystemExit("Each prop may have only one --prop-form")
    scene_materials = list(dict.fromkeys(args.scene_material))
    inferred_traits = retrieval_traits_for(args.request, args.shot, medium=args.medium)
    inferred_view_angles = list(
        dict.fromkeys(
            trait.removeprefix("view-angle:")
            for trait in inferred_traits
            if trait.startswith("view-angle:")
        )
    )
    if (
        args.view_angle
        and inferred_view_angles
        and any(value != args.view_angle for value in inferred_view_angles)
    ):
        raise SystemExit(
            "--view-angle conflicts with an explicit view direction in --request"
        )
    if not args.view_angle and len(inferred_view_angles) > 1:
        raise SystemExit(
            "The request contains multiple view directions; pass one explicit "
            "--view-angle or split the image into separate tasks"
        )
    view_angle = args.view_angle or (
        inferred_view_angles[0] if inferred_view_angles else None
    )
    if view_angle and f"view-angle:{view_angle}" not in inferred_traits:
        inferred_traits.append(f"view-angle:{view_angle}")
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
    if args.shot:
        command.extend(["--shot", args.shot])
    if view_angle:
        command.extend(["--view-angle", view_angle])
    for character, form in args.identity_form:
        if form not in FORM_VALUES:
            raise SystemExit(f"Unsupported form: {form}")
        command.extend(["--identity-form", f"{character}={form}"])
    for prop, form in prop_forms:
        if form not in FORM_VALUES:
            raise SystemExit(f"Unsupported prop form: {form}")
        command.extend(["--prop-form", f"{prop}={form}"])
    for material in scene_materials:
        command.extend(["--scene-material", material])
    effective_content_query = scene_query or args.content_query
    effective_content_focus = scene_focus or args.content_focus
    if effective_content_query:
        command.extend(["--content-query", effective_content_query])
        command.extend(["--content-focus", effective_content_focus])
        command.extend(["--content-provenance", args.content_provenance])
        command.extend(["--content-kind", "scene" if canonical_scene else "content"])
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    task_dir = Path(completed.stdout.strip().splitlines()[-1]).resolve()

    # Record the interpreter already running the planner. This keeps generated
    # command arrays directly executable on macOS, Linux, and Windows.
    launcher = sys.executable
    official_preferences = []
    if args.shot:
        official_preferences.extend(["--prefer-shot", args.shot])
    if view_angle:
        official_preferences.extend(["--prefer-view-angle", view_angle])
    official_commands = []
    for character, form in args.identity_form:
        official_commands.append(
            [
            launcher,
            str(SCRIPTS / "search_reference_index.py"),
            "--source",
            "official",
            "--role",
            "identity",
            "--subject",
            character,
            "--form",
            form,
            "--intent-text",
            args.request,
            *official_preferences,
            "--collapse-candidate-series",
            "--limit",
            str(args.candidate_limit),
            ]
        )
    for prop, form in prop_forms:
        official_commands.append(
            [
                launcher,
                str(SCRIPTS / "search_reference_index.py"),
                "--source",
                "official",
                "--role",
                "identity",
                "--subject",
                prop,
                "--form",
                form,
                "--intent-text",
                args.request,
                "--collapse-candidate-series",
                "--limit",
                str(args.candidate_limit),
            ]
        )
    style_source = "manga-curated" if args.medium == "manga" else "tv-curated"
    preferred_subject_forms = [
        value
        for character, form in args.identity_form
        for value in ("--prefer-subject-form", f"{character}={form}")
    ]
    combined_style_command = [
        launcher,
        str(SCRIPTS / "browse_curated_styles.py"),
        "--source",
        style_source,
        "--combined-rendering",
        "--role",
        "rendering",
        "--intent-text",
        args.request,
        *preferred_subject_forms,
    ]
    if view_angle:
        combined_style_command.extend(["--view-angle", view_angle])
    if args.shot:
        combined_style_command.extend(["--shot", args.shot])
    if canonical_scene:
        combined_style_command.extend(["--scene-exact-term", scene_query])
    combined_style_command.extend(
        ["--limit", str(args.candidate_limit), "--columns", "4"]
    )
    layers = [
        {
            "layer": 1,
            "source": "official",
            "identity_cards": [],
            "prepare_arguments": [],
            "primary_commands": official_commands,
            "retrieval_complete": True,
            "selection_budget": (
                "inspect at most four official setting-sheet candidates per focal "
                "character; one explicitly curated similar-content series occupies "
                "one candidate slot and its representative follows the current request, "
                "while every source remains indexed; choose "
                "one shot-matched source or the smallest focused "
                "crop that preserves the required face, form, costume, or construction; "
                "a declared view angle ranks matching official facets first. For a "
                "non-wide shot it must match an exact controlled view facet or a "
                "focused crop; a wide-shot may retain exact-form identity evidence "
                "and record view coverage as INSUFFICIENT. "
                "If the bounded result is insufficient, record INSUFFICIENT and stop "
                "retrieval; schema-5 "
                "face/profile/close-up/medium-shot tasks must crop an unmatched "
                "setting sheet before pre-generation validation; "
                "each declared canonical prop requires exact-form official coverage and "
                "may not be inferred from a style screenshot"
            ),
        },
        {
            "layer": 2,
            "source": style_source,
            "role": "combined-rendering",
            "primary_commands": [combined_style_command],
            "groups": ["character-style", "scene"],
            "retrieval_complete": True,
            "selection_budget": (
                "inspect this one bounded selected-medium result, grouped into exact-form "
                "character-style and scene-style candidates. Character candidates must "
                "use exact requested forms; an unrequested known character or wrong form "
                "is ineligible before ranking, and retrieval must never broaden to another "
                "character or form. Choose one anchor from each available group by "
                "default. When canonical scene identity is HIT but its scene-style "
                "coverage is INSUFFICIENT, retain that structural anchor and choose one "
                "additional scene-style anchor from the same bounded scene group; do "
                "not run another retrieval. Shot and view affect ranking inside this "
                "final result. "
                "For a wide-shot whose exact-form character anchor misses the requested "
                "view, record Layer 2 INSUFFICIENT without another retrieval. Record "
                "MISS or INSUFFICIENT for a missing group and let ImageGen "
                "construct the uncovered pose or scene."
            ),
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
                "--role",
                "content",
                "--exact-term",
                args.content_query,
                "--intent-text",
                args.content_focus,
            ]
            if include_shot and args.shot:
                parts.extend(["--shot", args.shot])
            parts.extend(["--limit", str(args.candidate_limit), "--columns", "4"])
            return parts

        layers.append(
            {
                "layer": len(layers) + 1,
                "role": "content",
                "need": args.content_focus,
                "selected_medium": {
                    "source": style_source,
                    "primary_commands": [content_command(style_source, True)],
                },
                "cross_medium_fallback": {
                    "source": fallback_content_source,
                    "allowed_after": ["MISS", "INSUFFICIENT"],
                    "primary_commands": [
                        content_command(fallback_content_source, True)
                    ],
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
            "--role",
            "continuity",
            *(["--shot", args.shot] if args.shot else []),
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "4",
        ]
        layers.append(
            {
                "layer": len(layers) + 1,
                "source": "selected-output",
                "primary_commands": [continuity_primary],
                "selection_budget": "at most one explicitly requested continuity precedent",
            }
        )

    plan = {
        "schema_version": 5,
        "task": task_dir.name,
        "gate": "Run one layer, inspect candidates, record HIT/MISS/INSUFFICIENT, then advance.",
        "mode": (
            "canonical-scene"
            if canonical_scene
            else "cross-medium-content"
            if args.content_query
            else ("continuity" if args.continuity else "fast-default")
        ),
        "candidate_limit": args.candidate_limit,
        "inferred_retrieval_traits": inferred_traits,
        "view_angle": view_angle,
        "character_style_fallbacks": [],
        "prop_forms": dict(prop_forms),
        "dominant_scene_materials": scene_materials,
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
        "canonical_scene": canonical_scene,
        "content_need": (
            {
                "query": effective_content_query,
                "focus": effective_content_focus,
                "kind": "scene" if canonical_scene else "content",
                "provenance": args.content_provenance,
            }
            if effective_content_query
            else None
        ),
        "layers": layers,
    }
    brief_path = task_dir / "brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    brief["retrieval_traits"] = inferred_traits
    if canonical_scene:
        brief["style_strategy"] = f"{args.medium}-character-style-canonical-scene"
        brief["scene"] = canonical_scene["label"]
        brief["canonical_scene"] = canonical_scene
    elif args.content_query:
        brief["style_strategy"] = f"{args.medium}-style-cross-medium-content"
    else:
        brief["style_strategy"] = (
            f"three-layer-{args.medium}-continuity"
            if args.continuity
            else f"two-layer-{args.medium}-fast"
        )
    rendering_map = build_rendering_map(brief)
    if rendering_map is not None:
        brief["rendering_map"] = rendering_map
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
