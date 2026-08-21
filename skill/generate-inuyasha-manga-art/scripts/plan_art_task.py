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
    official_commands = []
    official_fallback_commands = []
    official_view_fallback_commands = []
    official_unfaceted_fallback_commands = []
    for character, form in args.identity_form:
        base = [
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
            "--limit",
            str(args.candidate_limit),
        ]
        parts = list(base)
        if args.shot:
            parts.extend(["--shot", args.shot])
        if view_angle:
            parts.extend(["--view-angle", view_angle])
        official_commands.append(parts)
        if args.shot:
            shotless = list(base)
            if view_angle:
                shotless.extend(["--view-angle", view_angle])
            official_fallback_commands.append(shotless)
        if view_angle:
            viewless = list(base)
            if args.shot:
                viewless.extend(["--shot", args.shot])
            official_view_fallback_commands.append(viewless)
            official_unfaceted_fallback_commands.append(list(base))
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
                "--limit",
                str(args.candidate_limit),
            ]
        )
    style_source = "manga-curated" if args.medium == "manga" else "tv-curated"
    # Character-style evidence is eligible only when it depicts a requested
    # focal character in the exact requested form.  View and shot rank only
    # inside that set; no other character or form is an automatic fallback.
    common = []
    if args.shot:
        common.extend(["--shot", args.shot])
    preferred_subject_forms = [
        value
        for character, form in args.identity_form
        for value in ("--prefer-subject-form", f"{character}={form}")
    ]
    style_base = [
        launcher,
        str(SCRIPTS / "browse_curated_styles.py"),
        "--source",
        style_source,
        "--role",
        "rendering",
        "--reference-domain",
        "character-style",
        "--intent-text",
        args.request,
        *preferred_subject_forms,
    ]
    if view_angle:
        style_base.extend(["--view-angle", view_angle])
    style_primary = [
        *style_base,
        *common,
        "--limit",
        str(args.candidate_limit),
        "--columns",
        "3",
    ]
    style_fallback = [
        *style_base,
        "--limit",
        str(args.candidate_limit),
        "--columns",
        "3",
    ]
    layers = [
        {
            "layer": 1,
            "source": "official",
            "identity_cards": [],
            "prepare_arguments": [],
            "primary_commands": official_commands,
            "fallback_without_shot": official_fallback_commands,
            "fallback_without_view_angle": official_view_fallback_commands,
            "fallback_without_shot_or_view_angle": official_unfaceted_fallback_commands,
            "selection_budget": (
                "inspect at most three official setting-sheet candidates per focal "
                "character; choose one shot-matched source or the smallest focused "
                "crop that preserves the required face, form, costume, or construction; "
                "a declared view angle must match an exact controlled view facet. "
                "Viewless fallbacks may be inspected only to prepare the smallest "
                "focused crop and never count as view coverage; schema-5 "
                "face/profile/close-up/medium-shot tasks must crop an unmatched "
                "setting sheet before pre-generation validation; "
                "each declared canonical prop requires exact-form official coverage and "
                "may not be inferred from a style screenshot"
            ),
        },
        {
            "layer": 2,
            "source": style_source,
            "primary_commands": [style_primary],
            "fallback_without_shot": [style_fallback] if args.shot else [],
            "selection_budget": (
                "inspect one combined character-style candidate set containing only "
                "requested focal characters in their exact requested forms; any panel "
                "with an unrequested known character or wrong form is ineligible before "
                "ranking. Choose "
                "one anchor by default; add a second complementary anchor only after "
                "inspection records that the first is insufficient for a visible "
                "character-rendering relationship. These inputs control only linework, "
                "face/hair mark simplification, fabric marks, and garment value hierarchy. "
                "A declared view angle is a strong applicability signal and must be "
                "visibly covered before selection; it never grants pose authority. "
                "If the exact-character-form set is empty or visibly insufficient, record "
                "MISS or INSUFFICIENT and curate same-character, same-form evidence; never "
                "broaden to another character or form. "
                "Official evidence remains the identity authority; ignore action, "
                "interaction, expression, framing, and scene similarity."
            ),
        },
    ]
    if canonical_scene:
        scene_identity_command = [
            launcher,
            str(SCRIPTS / "browse_curated_styles.py"),
            "--source",
            style_source,
            "--reference-domain",
            "scene",
            "--role",
            "content",
            "--exact-term",
            scene_query,
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "3",
        ]
        layers.append(
            {
                "layer": len(layers) + 1,
                "role": "canonical-scene",
                "need": scene_focus,
                "source": style_source,
                "primary_commands": [scene_identity_command],
                "fallback_without_shot": [],
                "coverage_gate": {
                    "required_field": "scene_style_coverage",
                    "allowed_values": ["HIT", "INSUFFICIENT"],
                    "prepare_argument": "--scene-style-coverage ITEM_ID=HIT|INSUFFICIENT",
                },
                "after_miss_or_insufficient": "ImageGen constructs the canonical scene from the request; do not cross media",
                "selection_budget": (
                    "choose at most one exact scene-domain reference. It always controls "
                    "canonical structure; it controls scene rendering only after an "
                    "explicit scene_style_coverage=HIT. Otherwise record INSUFFICIENT. "
                    "It never controls visible characters, pose, action, expression, or framing"
                ),
            }
        )
        canonical_scene_style_command = [
            launcher,
            str(SCRIPTS / "browse_curated_styles.py"),
            "--source",
            style_source,
            "--reference-domain",
            "scene",
            "--role",
            "rendering",
            "--intent-text",
            args.request,
            "--exclude-exact-term",
            scene_query,
            *common,
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "3",
        ]
        canonical_scene_style_fallback = [
            launcher,
            str(SCRIPTS / "browse_curated_styles.py"),
            "--source",
            style_source,
            "--reference-domain",
            "scene",
            "--role",
            "rendering",
            "--intent-text",
            args.request,
            "--exclude-exact-term",
            scene_query,
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "3",
        ]
        layers.append(
            {
                "layer": len(layers) + 1,
                "role": "scene-style-fallback",
                "source": style_source,
                "run_when": [
                    "canonical scene result is MISS or INSUFFICIENT",
                    "canonical scene result is HIT and scene_style_coverage is INSUFFICIENT",
                ],
                "skip_when": "canonical scene result is HIT and scene_style_coverage is HIT",
                "primary_commands": [canonical_scene_style_command],
                "fallback_without_shot": (
                    [canonical_scene_style_fallback] if args.shot else []
                ),
                "scene_construction": (
                    "ImageGen when canonical scene identity is MISS or INSUFFICIENT"
                ),
                "selection_budget": (
                    "choose exactly one non-canonical scene-domain rendering anchor "
                    "when this conditional layer runs"
                ),
            }
        )
    else:
        scene_style_command = [
            launcher,
            str(SCRIPTS / "browse_curated_styles.py"),
            "--source",
            style_source,
            "--reference-domain",
            "scene",
            "--role",
            "rendering",
            "--intent-text",
            args.request,
            *common,
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "3",
        ]
        scene_style_fallback = [
            launcher,
            str(SCRIPTS / "browse_curated_styles.py"),
            "--source",
            style_source,
            "--reference-domain",
            "scene",
            "--role",
            "rendering",
            "--intent-text",
            args.request,
            "--limit",
            str(args.candidate_limit),
            "--columns",
            "3",
        ]
        layers.append(
            {
                "layer": len(layers) + 1,
                "role": "scene-style",
                "source": style_source,
                "primary_commands": [scene_style_command],
                "fallback_without_shot": [scene_style_fallback] if args.shot else [],
                "scene_construction": "ImageGen",
                "selection_budget": (
                    "choose one scene-domain rendering anchor. It controls materials, "
                    "weather, negative space, black-white mass, and detail falloff; "
                    "when scene-economy traits are present its density is a ceiling and may "
                    "not transfer onto the character; "
                    "ImageGen controls scene construction, staging, and all actions"
                ),
            }
        )
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
            parts.extend(["--limit", str(args.candidate_limit), "--columns", "3"])
            return parts

        layers.append(
            {
                "layer": len(layers) + 1,
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
            "--role",
            "continuity",
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
            "--role",
            "continuity",
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
