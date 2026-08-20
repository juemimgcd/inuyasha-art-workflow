#!/usr/bin/env python3
"""Shared task-schema, prompt, and feedback helpers for the art workflow."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from workflow_common import atomic_write_text, resolve_recorded_path

BRIEF_SCHEMA_VERSION = 5
RESULT_SCHEMA_VERSION = 3
ATTEMPT_SCHEMA_VERSION = 2
LATENCY_SCHEMA_VERSION = 2
QA_SCHEMA_VERSION = 2
REFERENCE_STRATEGY_SCHEMA_VERSION = 1
RENDERING_MAP_SCHEMA_VERSION = 1
SPLIT_DOMAIN_REFERENCE_STRATEGY = {
    "schema_version": REFERENCE_STRATEGY_SCHEMA_VERSION,
    "mode": "split-domain",
    "required_style_scopes": ["character", "scene"],
    "canonical_scene_style": "coverage-gated",
}
QA_DIMENSIONS = (
    ("character_identity", "人物身份"),
    ("character_style", "人物画风"),
    ("scene_identity", "场景身份"),
    ("scene_style", "场景画风"),
    ("action_request", "动作与请求"),
    ("composition_integration", "人物与场景结合、镜头和构图"),
)
QA_WARNING_DIMENSIONS = {"character_style", "scene_style"}
QA_WARNING_CHECK_CATEGORIES = {"medium"}


def new_split_domain_reference_strategy() -> dict[str, Any]:
    """Return a fresh structured strategy for a new character-plus-scene task."""
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in SPLIT_DOMAIN_REFERENCE_STRATEGY.items()
    }


def is_split_domain_task(
    brief: dict[str, Any], qa: dict[str, Any] | None = None
) -> bool:
    """Recognize current and compatibility split-domain new tasks in one place."""
    if task_intent(brief) != "new":
        return False
    strategy = brief.get("reference_strategy")
    if isinstance(strategy, dict) and strategy.get("mode") == "split-domain":
        return True
    if isinstance(qa, dict) and qa.get("schema_version") == QA_SCHEMA_VERSION:
        return True
    return "character-style" in str(brief.get("style_strategy", ""))


def reference_strategy_failures(brief: dict[str, Any]) -> list[str]:
    """Validate a structured strategy when the brief declares one."""
    strategy = brief.get("reference_strategy")
    if strategy is None:
        return []
    if not isinstance(strategy, dict):
        return ["brief.reference_strategy must be an object"]
    failures = []
    if strategy.get("schema_version") != REFERENCE_STRATEGY_SCHEMA_VERSION:
        failures.append(
            "brief.reference_strategy.schema_version must be "
            f"{REFERENCE_STRATEGY_SCHEMA_VERSION}"
        )
    if strategy.get("mode") != "split-domain":
        failures.append("brief.reference_strategy.mode must be split-domain")
    if strategy.get("required_style_scopes") != ["character", "scene"]:
        failures.append(
            "brief.reference_strategy.required_style_scopes must be "
            "['character', 'scene']"
        )
    if strategy.get("canonical_scene_style") != "coverage-gated":
        failures.append(
            "brief.reference_strategy.canonical_scene_style must be coverage-gated"
        )
    return failures


def build_rendering_map(brief: dict[str, Any]) -> dict[str, Any] | None:
    """Derive a compact, editable manga rendering plan from the task brief.

    The map names positive relationships only. It does not select references or
    grant authority; the manifest remains the source of truth for that.
    """
    if brief.get("medium") != "manga":
        return None
    intent = task_intent(brief)
    shot = brief.get("shot")
    category = brief.get("change_category")
    scope = brief.get("change_scope")
    scoped_change = (
        intent in {"edit", "microfix"}
        and category in SCOPED_STYLE_CHANGE_CATEGORIES
        and scope in CHANGE_SCOPES
    )
    character_authority = (
        "character-style"
        if intent == "new" or (scoped_change and scope == "character")
        else "target"
    )
    scene_authority = (
        "scene-style"
        if intent == "new" or (scoped_change and scope == "scene")
        else "target"
    )
    materials = [
        str(value).strip()
        for value in brief.get("dominant_scene_materials") or []
        if str(value).strip()
    ]
    material_phrase = ", ".join(materials) if materials else "the requested setting"
    character_focal = shot in {
        "face",
        "profile",
        "close-up",
        "medium-shot",
        "upper-body",
        "two-shot",
    }
    environment_dominant = shot == "wide-shot" or {
        "scene-economy:authored-negative-space",
        "detail-falloff:strong",
    }.issubset(set(brief.get("retrieval_traits") or []))
    if environment_dominant:
        focal_plane = (
            f"resolve the route, major axes, overlap, scale, and ground contact in "
            f"{material_phrase}"
        )
        near_plane = (
            f"use decisive contours and a few directional material marks for "
            f"{material_phrase}"
        )
        middle_plane = "group repeated forms into a few outline, black, and tone masses"
        far_plane = "reduce each successive depth layer to fewer internal marks"
        paper_white = "reserve contiguous open sky, mist, water, or ground as paper white"
    elif character_focal:
        focal_plane = "fully resolve the focal face, hands, contact, and costume overlaps"
        near_plane = f"state only the setting cues needed to locate {material_phrase}"
        middle_plane = "group the remaining setting into a few quiet shapes"
        far_plane = "leave distant setting open or in one restrained tone"
        paper_white = "protect clean paper around the focal face and silhouette"
    else:
        focal_plane = "fully resolve the requested action, contact, and spatial relationship"
        near_plane = f"state {material_phrase} with selective structural marks"
        middle_plane = "group nonfocal forms into clear silhouettes and one tone family"
        far_plane = "let distant forms lose interior marks visibly"
        paper_white = "keep deliberate paper-white intervals between focal groups"
    return {
        "schema_version": RENDERING_MAP_SCHEMA_VERSION,
        "character": {
            "authority": character_authority,
            "resolve": (
                "identity-bearing eyes, bangs, jaw, hair silhouette, costume layers, "
                "hands, and contact chains"
            ),
            "group": (
                "hair into readable lock masses and fabric into broad folds from "
                "support or contact points"
            ),
            "quiet": "keep skin clean and let secondary strands and folds fall away",
        },
        "scene": {
            "authority": scene_authority,
            "focal_plane": focal_plane,
            "near_plane": near_plane,
            "middle_plane": middle_plane,
            "far_plane": far_plane,
            "paper_white": paper_white,
        },
        "value_hierarchy": {
            "paper_white": "skin, highlights, and authored negative space",
            "flat_black": "major hair, night, silhouette, or effect masses supported by evidence",
            "middle_tone": "one restrained separator for garments, atmosphere, or distance",
        },
    }


def rendering_map_failures(brief: dict[str, Any]) -> list[str]:
    """Validate a declared rendering map while leaving historical briefs readable."""
    rendering_map = brief.get("rendering_map")
    if rendering_map is None:
        return []
    if brief.get("medium") != "manga":
        return ["brief.rendering_map is valid only for manga tasks"]
    if not isinstance(rendering_map, dict):
        return ["brief.rendering_map must be an object"]
    failures: list[str] = []
    if rendering_map.get("schema_version") != RENDERING_MAP_SCHEMA_VERSION:
        failures.append(
            f"brief.rendering_map.schema_version must be {RENDERING_MAP_SCHEMA_VERSION}"
        )
    sections = {
        "character": ("authority", "resolve", "group", "quiet"),
        "scene": (
            "authority",
            "focal_plane",
            "near_plane",
            "middle_plane",
            "far_plane",
            "paper_white",
        ),
        "value_hierarchy": ("paper_white", "flat_black", "middle_tone"),
    }
    for section, fields in sections.items():
        value = rendering_map.get(section)
        if not isinstance(value, dict):
            failures.append(f"brief.rendering_map.{section} must be an object")
            continue
        for field in fields:
            if not isinstance(value.get(field), str) or not value[field].strip():
                failures.append(
                    f"brief.rendering_map.{section}.{field} must be a non-empty string"
                )
    for section in ("character", "scene"):
        value = rendering_map.get(section)
        if isinstance(value, dict) and value.get("authority") not in {
            "character-style",
            "scene-style",
            "target",
        }:
            failures.append(
                f"brief.rendering_map.{section}.authority is invalid"
            )
    return failures


def qa_acceptance_failures(qa: Any) -> list[str]:
    """Return blocking QA defects for a new split-domain acceptance."""
    if not isinstance(qa, dict):
        return ["qa must be an object"]
    failures: list[str] = []
    if qa.get("schema_version") != QA_SCHEMA_VERSION:
        failures.append(f"qa.schema_version must be {QA_SCHEMA_VERSION}")
    dimensions = qa.get("dimensions")
    if not isinstance(dimensions, list):
        return [*failures, "qa.dimensions must be a list"]
    expected_count = len(QA_DIMENSIONS)
    if len(dimensions) != expected_count:
        failures.append(f"qa.dimensions must contain exactly {expected_count} rows")
    object_rows = [row for row in dimensions if isinstance(row, dict)]
    if len(object_rows) != len(dimensions):
        failures.append("qa.dimensions must contain objects")
    raw_dimension_ids = [row.get("id") for row in object_rows]
    if any(not isinstance(dimension_id, str) for dimension_id in raw_dimension_ids):
        failures.append("qa dimension IDs must be strings")
    dimension_ids = [
        dimension_id
        for dimension_id in raw_dimension_ids
        if isinstance(dimension_id, str)
    ]
    if len(dimension_ids) != len(set(dimension_ids)):
        failures.append("qa.dimensions must not contain duplicate IDs")
    by_id = {
        row.get("id"): row for row in object_rows if isinstance(row.get("id"), str)
    }
    expected = {dimension_id for dimension_id, _ in QA_DIMENSIONS}
    if set(by_id) != expected:
        failures.append("qa.dimensions must contain exactly the six required dimensions")
    for dimension_id, label in QA_DIMENSIONS:
        row = by_id.get(dimension_id) or {}
        status = row.get("status")
        if status == "warning" and dimension_id not in QA_WARNING_DIMENSIONS:
            failures.append(f"QA dimension warning is not allowed: {label}")
        elif status not in {"pass", "warning"}:
            failures.append(f"QA dimension is not pass: {label}")
        if status in {"pass", "warning"} and not str(row.get("note", "")).strip():
            failures.append(f"QA dimension {status} has no note: {label}")
    checks = qa.get("checks")
    if not isinstance(checks, list) or not checks:
        failures.append("qa.checks must be a non-empty list")
        checks = []
    for check in checks:
        if not isinstance(check, dict):
            failures.append("qa.checks must contain objects")
            continue
        status = check.get("status")
        category = check.get("category")
        if status == "warning" and category not in QA_WARNING_CHECK_CATEGORIES:
            failures.append(
                "QA check warning is only allowed for medium: "
                f"{check.get('check', '[unnamed check]')}"
            )
        elif status not in {"pass", "warning", "n/a"}:
            failures.append(
                f"QA check is not complete: {check.get('check', '[unnamed check]')}"
            )
        if status in {"pass", "warning"} and not str(check.get("note", "")).strip():
            failures.append(
                f"QA check {status} has no note: "
                f"{check.get('check', '[unnamed check]')}"
            )
    return failures
DEFAULT_NEW_PRE_GENERATION_TARGET_SECONDS = 90
DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS = 30
DEFAULT_POST_GENERATION_TARGET_SECONDS = 30
DEFAULT_MAX_TECHNICAL_RETRIES = 1
INTENT_VALUES = ("new", "edit", "microfix")
CHANGE_CATEGORIES = (
    "identity",
    "form",
    "costume",
    "anatomy",
    "construction",
    "medium",
    "composition",
    "background",
    "tone",
    "polish",
)
CHANGE_SCOPES = ("character", "scene")
CHANGE_SCOPE_SCHEMA_VERSION = 1
SCOPED_STYLE_CHANGE_CATEGORIES = {"medium", "tone"}
IDENTITY_LEDGERS_PATH = (
    Path(__file__).resolve().parent.parent / "references" / "identity-ledgers.json"
)


def parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed


def elapsed_seconds(started_at: str, finished_at: str) -> float:
    elapsed = (
        parse_timestamp(finished_at) - parse_timestamp(started_at)
    ).total_seconds()
    if elapsed < 0:
        raise ValueError("finished timestamp cannot precede started timestamp")
    return round(elapsed, 1)


def latency_budget(brief: dict[str, Any]) -> dict[str, int]:
    """Return controllable phase targets without constraining model latency.

    Legacy schema-1 budgets remain readable. Their preparation and handoff
    values become soft phase targets; the old total response and generation
    budgets intentionally do not participate in gating.
    """
    configured = brief.get("latency_budget") or {}
    intent = brief.get("intent") or (
        "edit" if brief.get("deliverable") == "edit" else "new"
    )
    default_pre_generation = (
        DEFAULT_NEW_PRE_GENERATION_TARGET_SECONDS
        if intent == "new"
        else DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS
    )
    return {
        "schema_version": LATENCY_SCHEMA_VERSION,
        "pre_generation_target_seconds": int(
            configured.get(
                "pre_generation_target_seconds",
                configured.get("preparation_budget_seconds", default_pre_generation),
            )
        ),
        "post_generation_target_seconds": int(
            configured.get(
                "post_generation_target_seconds",
                configured.get(
                    "handoff_budget_seconds", DEFAULT_POST_GENERATION_TARGET_SECONDS
                ),
            )
        ),
        "max_technical_retries": int(
            configured.get("max_technical_retries", DEFAULT_MAX_TECHNICAL_RETRIES)
        ),
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def result_output(result: dict[str, Any]) -> Path | None:
    for key in ("output", "task_output", "accepted_output"):
        if result.get(key):
            return resolve_recorded_path(result[key])
    return None


def task_intent(brief: dict[str, Any]) -> str:
    intent = brief.get("intent")
    if intent in INTENT_VALUES:
        return intent
    return "edit" if brief.get("deliverable") == "edit" else "new"


def style_scope_for_entry(
    entry: dict[str, Any],
    catalog_reference_domain: str | None = None,
) -> str | None:
    """Return an explicit scope or a legacy catalog-derived rendering domain."""
    if "style_scope" in entry and entry.get("style_scope") is not None:
        scope = entry.get("style_scope")
        return scope if scope in CHANGE_SCOPES else None
    reference_domain = entry.get("reference_domain") or catalog_reference_domain
    if reference_domain == "character-style":
        return "character"
    if reference_domain == "scene":
        return "scene"
    return None


def scoped_style_failures(
    brief: dict[str, Any],
    manifest: dict[str, Any],
    *,
    require_scope: bool,
    catalog_reference_domains: dict[str, str] | None = None,
) -> list[str]:
    """Validate that a style-changing edit uses one matching authority domain."""
    intent = task_intent(brief)
    category = brief.get("change_category")
    scope = brief.get("change_scope")
    contract_version = brief.get("change_scope_schema_version")
    style_entries = [
        entry
        for entry in manifest.get("references", [])
        if entry.get("role") == "style"
    ]
    failures: list[str] = []
    if contract_version is not None and (
        type(contract_version) is not int
        or contract_version != CHANGE_SCOPE_SCHEMA_VERSION
    ):
        failures.append(
            "brief.change_scope_schema_version must be "
            f"{CHANGE_SCOPE_SCHEMA_VERSION}"
        )
        return failures
    if scope is not None and scope not in CHANGE_SCOPES:
        failures.append(
            "brief.change_scope must be one of: " + ", ".join(CHANGE_SCOPES)
        )
        return failures
    if intent not in {"edit", "microfix"}:
        if scope is not None:
            failures.append("brief.change_scope is only valid for edit or microfix")
        return failures
    if category not in SCOPED_STYLE_CHANGE_CATEGORIES:
        if scope is not None and style_entries:
            mismatches = [
                entry.get("item_id") or "[missing]"
                for entry in style_entries
                if style_scope_for_entry(
                    entry,
                    (catalog_reference_domains or {}).get(entry.get("item_id")),
                )
                != scope
            ]
            if mismatches:
                failures.append(
                    f"style reference scope does not match brief.change_scope={scope}: "
                    + ", ".join(mismatches)
                )
        return failures
    if scope is None:
        if require_scope or contract_version == CHANGE_SCOPE_SCHEMA_VERSION:
            failures.append(
                f"{intent} {category} changes require brief.change_scope "
                "(character or scene)"
            )
        return failures
    if len(style_entries) != 1:
        return failures
    style_entry = style_entries[0]
    actual_scope = style_scope_for_entry(
        style_entry,
        (catalog_reference_domains or {}).get(style_entry.get("item_id")),
    )
    if actual_scope != scope:
        failures.append(
            f"{intent} {category} change_scope={scope} requires one {scope}-style "
            f"reference, got {actual_scope or 'unscoped'}: "
            f"{style_entries[0].get('item_id') or '[missing]'}"
        )
    return failures


def prompt_limit(intent: str) -> int:
    return {"new": 7000, "edit": 3500, "microfix": 1800}[intent]


def _reference_lines(manifest: dict[str, Any]) -> list[str]:
    lines = []
    for index, entry in enumerate(manifest.get("references", []), 1):
        role = entry.get("role", "unknown")
        instruction = entry.get("instructions") or "Use only for its declared role."
        lines.append(f"- Input {index} ({role}): {instruction}")
    return lines or ["- No references prepared yet."]


def character_style_assignments(
    brief: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Prefer exact style evidence without turning rendering into identity lookup."""
    targets = brief.get("character_style_targets") or {}
    style_entries = [
        (index, entry)
        for index, entry in enumerate(manifest.get("references", []), 1)
        if entry.get("role") == "style" and entry.get("style_scope") == "character"
    ]
    assignments: dict[str, dict[str, Any]] = {}
    for character, form in targets.items():
        key = f"{character}={form}"
        exact = [
            index
            for index, entry in style_entries
            if form in ((entry.get("subject_forms") or {}).get(character) or [])
        ]
        same_character = [
            index
            for index, entry in style_entries
            if character in (entry.get("subject_forms") or {})
            or character in (entry.get("subjects") or [])
        ]
        if exact:
            tier = "exact-character-form"
            inputs = exact
        elif same_character:
            tier = "same-character-compatible"
            inputs = same_character
        else:
            tier = "general-selected-medium"
            inputs = [index for index, _ in style_entries]
        assignments[key] = {"inputs": inputs, "tier": tier}
    return assignments


def character_style_coverage(
    brief: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, list[int]]:
    """Return the best available style inputs for each focal character-form."""
    return {
        target: assignment["inputs"]
        for target, assignment in character_style_assignments(brief, manifest).items()
    }


def character_style_coverage_failures(
    brief: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    coverage = character_style_coverage(brief, manifest)
    return [
        f"missing selected-medium character-style evidence: {target}"
        for target, inputs in coverage.items()
        if not inputs
    ]


def _character_style_mapping_clause(
    brief: dict[str, Any], manifest: dict[str, Any]
) -> str:
    assignments = character_style_assignments(brief, manifest)
    if not assignments:
        return ""
    lines = []
    for target, assignment in assignments.items():
        inputs = assignment["inputs"]
        input_labels = ", ".join(f"Input {index}" for index in inputs) or "MISSING"
        tier = {
            "exact-character-form": "exact",
            "same-character-compatible": "same-character",
            "general-selected-medium": "general",
        }[assignment["tier"]]
        lines.append(f"- {target}: {input_labels} ({tier})")
    return (
        "\n\nPer-character rendering map:\n"
        + "\n".join(lines)
        + "\nMapped inputs control selected-medium contours, marks, folds, and values. "
        "Exact is preferred. Compatible/general never controls identity, form, costume, "
        "or anatomy; official does. MISSING blocks the character-style layer."
    )


def _cross_medium_clause(manifest: dict[str, Any], medium: str) -> str:
    lines = []
    for index, entry in enumerate(manifest.get("references", []), 1):
        if entry.get("role") != "content" or not entry.get("cross_medium"):
            continue
        source_medium = entry.get("evidence_medium") or "source-medium"
        focus = entry.get("focus") or "the declared exact content"
        lines.append(
            f"- Input {index}: translate only `{focus}` from {source_medium} into "
            f"{medium}; ignore the source medium's palette, contours, shading, "
            "textures, background grammar, framing, and character rendering."
        )
    if not lines:
        return ""
    return "\n\nCross-medium content conversion:\n" + "\n".join(lines)


def _medium_construction(medium: str, shot: str | None = None) -> str:
    if medium != "manga":
        return "Use the selected medium's inspected rendering grammar."
    if shot == "wide-shot":
        return (
            "Make this read as a direct, page-ready late-1990s serialized manga "
            "establishing shot. Treat information as a finite narrative budget: "
            "keep coherent axes, scale, depth, overlap, and ground contact, then "
            "concentrate marks only where they clarify the focal path. Organize the "
            "scene with large silhouettes, authored white-paper intervals, decisive "
            "flat black masses, and one restrained middle-tone family. Before secondary "
            "marks, reserve contiguous paper-white fields from open scene shapes and keep "
            "them unfilled. Collapse repeated foliage, architecture, "
            "and terrain into a few outline, flat-black, or restrained-tone groups. Let "
            "contours open or break when structure stays legible. Give selective texture "
            "only to the nearest informative plane; every successive depth layer must lose "
            "internal marks visibly, so detail falls away clearly. "
            "Render structural geometry completely but leave surface finish deliberately "
            "selective. Preserve recognizable materials, weather, and light required by "
            "the request, while limiting nonfocal surface "
            "marks to the chosen scene reference's information budget. Do not distribute "
            "the same finish density across every surface. If a small thumbnail reads mainly as uniform "
            "fine texture instead of a few clear white, black, and middle-tone masses, "
            "the rendering fails even when the perspective is correct. "
            "Complete objects and correct perspective do not excuse a globally engraved finish. "
            "Apply the selected style anchor's same economy consistently across every "
            "scene material instead of completing each surface independently. "
            "Keep every canonical garment component and overlap defined by official "
            "identity, but redraw it with the style reference's contour, fabric, fold, "
            "and paper-white, flat-black, and restrained-tone hierarchy. Never copy the "
            "style source's costume design."
        )
    return (
        "Make it read first as a late-1990s serialized black-and-white manga image, "
        "not a polished monochrome illustration or under-rendered coloring-book outline. Follow the "
        "mapped character-style inputs with economical ink shapes, decisive contour "
        "hierarchy, open paper-white, flat-black masses, and selective tone. Preserve the "
        "identity-bearing eye shapes, bangs, jaw, hair silhouette, costume layers, hands, "
        "contact, and required setting cues. Concentrate marks at the narrative focus "
        "and let nonfocal detail fall away. Keep every canonical garment component and "
        "overlap defined by official identity, but redraw it with the style reference's "
        "paper-white, flat-black, and restrained-tone hierarchy. Never copy the style "
        "source's costume design. "
        "Economy means selecting the right marks, "
        "not merely minimizing them."
    )


def _scene_economy_clause(brief: dict[str, Any]) -> str:
    traits = set(brief.get("retrieval_traits") or [])
    if brief.get("medium") != "manga" or not {
        "scene-economy:authored-negative-space",
        "detail-falloff:strong",
    }.issubset(traits):
        return ""
    return (
        "\nScene-density ceiling: the scene reference supplies material grouping, "
        "weather, value grouping, and distance falloff—not every visible mark. Preserve "
        "its contiguous paper-white shapes before secondary marks; group repeated forms, "
        "and visibly simplify each successive depth layer. Keep nonfocal architecture, "
        "rain, reflections, and texture at or below the reference's economical density. "
        "Never transfer the scene "
        "reference's texture frequency, contour density, black coverage, or lighting "
        "finish onto the character. The character must follow only the character-style "
        "anchor's face, hair, fabric, fold, and value treatment."
    )


def _manga_finish_calibration(
    medium: str,
    intent: str,
    manifest: dict[str, Any],
    change_category: str | None = None,
    change_scope: str | None = None,
) -> str:
    if medium != "manga":
        return ""
    if (
        change_category in SCOPED_STYLE_CHANGE_CATEGORIES
        and change_scope == "character"
    ):
        return (
            "\nCharacter-scope manga calibration: the selected character-style "
            "reference controls only character contour rhythm, face/hair marks, "
            "fabric/fold treatment, and garment value hierarchy. The target alone "
            "controls scene materials, negative space, background density, and scene "
            "black-white/tone grouping; do not recalibrate or redraw that scene domain."
        )
    if (
        change_category in SCOPED_STYLE_CHANGE_CATEGORIES
        and change_scope == "scene"
    ):
        return (
            "\nScene-scope manga calibration: the selected scene-style reference "
            "controls only environmental material abstraction, negative space, "
            "background density, black-white mass, tone restraint, and distance "
            "falloff. The target alone controls every character's contour, face/hair, "
            "fabric/folds, and garment value hierarchy; do not recalibrate or redraw "
            "that character domain."
        )
    if intent == "new":
        return (
            "\nManga finish calibration: selected character and scene references "
            "control contour rhythm, information density, material abstraction, "
            "negative space, and black-white/tone hierarchy. Concentrate marks at "
            "identity, action, contact, and setting cues; let nonfocal information "
            "fall away. Preserve requested scene phenomena, rendered with selective "
            "reference-matched marks rather than uniform refinement. Monochrome "
            "output or screen tone alone is insufficient."
        )
    style_scopes = {
        scope
        for entry in manifest.get("references", [])
        if entry.get("role") == "style"
        and (scope := style_scope_for_entry(entry)) is not None
    }
    if not style_scopes:
        return (
            "\nTarget-only manga preservation: no external style reference is "
            "attached. Keep the target's existing contour rhythm, information "
            "density, material abstraction, negative space, and black-white/tone "
            "hierarchy unchanged outside the named edit. Do not invent or infer a "
            "separate character-style or scene-style authority."
        )
    if style_scopes == {"character"}:
        return (
            "\nCharacter-reference manga calibration: the selected character-style "
            "reference controls only character contour rhythm, face/hair marks, "
            "fabric/fold treatment, and garment value hierarchy. The target controls "
            "scene materials, negative space, background density, and scene values."
        )
    if style_scopes == {"scene"}:
        return (
            "\nScene-reference manga calibration: the selected scene-style reference "
            "controls only environmental material abstraction, negative space, "
            "background density, black-white mass, tone restraint, and distance "
            "falloff. The target controls all character marks and garment values."
        )
    return (
        "\nManga finish calibration: selected character and scene references control "
        "contour rhythm, information density, material abstraction, negative space, "
        "and black-white/tone hierarchy. Concentrate marks at identity, action, contact, "
        "and setting cues; let nonfocal information fall away. Preserve requested scene "
        "phenomena, rendered with selective reference-matched marks rather than uniform "
        "refinement. Monochrome output or screen tone alone is insufficient."
    )


def _contact_topology_clause(brief: dict[str, Any]) -> str:
    """Compile explicit count and visibility requirements for named hand contact."""
    text = " ".join(
        str(brief.get(key) or "") for key in ("request", "change_request")
    )
    if "双手" not in text:
        return ""
    return (
        "\nNamed contact topology: `双手` requires exactly two distinct, visible hands. "
        "Both hands must participate in the requested action rather than hiding one "
        "behind hair, cloth, a body, or the frame. Trace each hand through every named "
        "prop and body-part contact in one mechanically continuous chain; reject a "
        "missing hand, an ambiguous fused hand, floating contact, or interpenetration."
    )


def _manga_finish_preservation(medium: str) -> str:
    if medium != "manga":
        return ""
    return (
        "\nDo not drift toward extra digital polish or strip away "
        "identity-critical face, hair, costume, interaction, or setting cues."
    )


def _manga_medium_edit_clause(
    medium: str,
    change_category: str | None,
    change_scope: str | None,
) -> str:
    if (
        medium != "manga"
        or change_category not in SCOPED_STYLE_CHANGE_CATEGORIES
        or change_scope not in CHANGE_SCOPES
    ):
        return ""
    if change_scope == "character":
        return (
            "\nCharacter-rendering replacement is the named edit. Apply the "
            "character-style reference only to character contour rhythm, face and "
            "hair linework, fabric and fold treatment, and the relative paper-white, "
            "flat-black, and restrained halftone hierarchy of the target's canonical "
            "garment components. Preserve official costume construction and preserve "
            "the target's scene materials, water, rocks, vegetation, weather, "
            "background density, composition, pose, expression, contact, and spatial "
            "relationships. Do not transfer character mark density onto the scene. "
            "A garment-value change that leaves the character generic, changes its "
            "costume design, or redraws the environment fails this scoped edit."
        )
    return (
        "\nScene-rendering replacement is the named edit. Apply the scene-style "
        "reference only to environmental materials, water, rocks, vegetation, "
        "weather, negative space, black-white mass, tone restraint, and distance "
        "falloff. Preserve every character's face, hair silhouette and linework, "
        "costume components, fabric and fold treatment, and existing garment "
        "paper-white/flat-black/halftone value hierarchy exactly from the target. "
        "Do not remove character strands or folds, retone clothing, or transfer "
        "scene texture frequency onto character anatomy. Preserve composition, pose, "
        "expression, contact, and spatial relationships. A scene correction that "
        "changes character rendering or garment values fails this scoped edit."
    )


def _manga_wide_edit_lock(medium: str, intent: str, shot: str | None) -> str:
    if medium != "manga" or intent != "edit" or shot != "wide-shot":
        return ""
    return (
        "\nWide-shot preservation lock: use the target's framing, crop, camera "
        "distance, character scale and placement, major object positions, "
        "perspective axes, and overall black-white distribution as fixed "
        "authority unless the named request explicitly changes one of them. "
        "Do not enlarge the character, recrop or recompose the scene, add "
        "large new black areas, or dramatize the staging merely to make the "
        "manga style more obvious. Economy is not uniform simplification across "
        "the canvas. Correct the finish locally through tapered or selectively "
        "broken contours, clustered marks, selective detail density, and "
        "distance falloff while preserving the target's wide-shot balance."
    )


def identity_requirements(
    character: str, form: str, retrieval_traits: list[str] | set[str] = ()
) -> list[str]:
    """Return shared observable identity constraints for one character-form."""
    ledgers = {}
    if IDENTITY_LEDGERS_PATH.is_file():
        ledgers = read_json(IDENTITY_LEDGERS_PATH).get("characters", {})
    profile = ledgers.get(character, {})
    traits = set(retrieval_traits)
    form_record = profile.get("forms", {}).get(form, [])
    if isinstance(form_record, dict):
        form_details = list(form_record.get("features", []))
        topology = form_record.get("topology") or {}
        sequence = [
            str(value).strip()
            for value in topology.get("connected_sequence", [])
            if str(value).strip()
        ]
        if sequence:
            form_details.append("连续结构：" + " → ".join(sequence))
        counts = topology.get("counts") or {}
        if counts:
            form_details.append(
                "明确数量："
                + "、".join(f"{name}×{count}" for name, count in counts.items())
            )
    else:
        form_details = list(form_record)
    return [
        *profile.get("common", []),
        *form_details,
        *(
            profile.get("view_traits", {}).get(form, {}).get("profile", [])
            if "view-angle:profile" in traits
            else []
        ),
        *profile.get("exclusions", []),
    ]


def _identity_lines(brief: dict[str, Any]) -> list[str]:
    forms = brief.get("identity_forms") or {}
    costumes = brief.get("forms_and_costumes") or []
    retrieval_traits = brief.get("retrieval_traits") or []
    lines = []
    for name, form in forms.items():
        details = identity_requirements(name, form, retrieval_traits)
        suffix = "；".join(details) if details else f"required form `{form}`"
        lines.append(f"- {name} ({form}): {suffix}")
    default_costumes = {f"{name}: {form}" for name, form in forms.items()}
    lines.extend(
        f"- {value}" for value in costumes if value and value not in default_costumes
    )
    return lines or ["- No named focal character."]


def _prop_lines(brief: dict[str, Any]) -> list[str]:
    forms = brief.get("prop_forms") or {}
    retrieval_traits = brief.get("retrieval_traits") or []
    lines = []
    for name, form in forms.items():
        details = identity_requirements(name, form, retrieval_traits)
        suffix = "；".join(details) if details else f"required form `{form}`"
        lines.append(f"- {name} ({form}): {suffix}")
    return lines or ["- No named canonical prop."]


def _dominant_material_clause(brief: dict[str, Any]) -> str:
    materials = [
        str(value).strip()
        for value in brief.get("dominant_scene_materials") or []
        if str(value).strip()
    ]
    if brief.get("medium") != "manga" or not materials:
        return ""
    return (
        "\nScene-material scope: "
        + ", ".join(materials)
        + ". These labels identify where the primary style anchor's information "
        "budget must be transferred; they are not separate detailing targets or "
        "reasons to add one style input per material. Use the same mark grouping, "
        "black-white mass, tone restraint, and distance falloff across them."
    )


def _rendering_map_clause(brief: dict[str, Any]) -> str:
    """Compile the stored rendering map into a short positive instruction block."""
    rendering_map = brief.get("rendering_map")
    if brief.get("medium") != "manga" or not isinstance(rendering_map, dict):
        return ""
    character = rendering_map.get("character") or {}
    scene = rendering_map.get("scene") or {}
    values = rendering_map.get("value_hierarchy") or {}
    intent = task_intent(brief)
    category = brief.get("change_category")
    scope = brief.get("change_scope")
    scoped_change = (
        intent in {"edit", "microfix"}
        and category in SCOPED_STYLE_CHANGE_CATEGORIES
        and scope in CHANGE_SCOPES
    )
    if intent == "microfix":
        if not scoped_change:
            return ""
        if scope == "character":
            return (
                "\nRendering map: resolve "
                + str(character.get("resolve", "")).strip()
                + "; "
                + str(character.get("quiet", "")).strip()
                + ". Keep scene marks and values target-locked."
            )
        return (
            "\nRendering map: "
            + str(scene.get("focal_plane", "")).strip()
            + "; "
            + str(scene.get("far_plane", "")).strip()
            + "; "
            + str(scene.get("paper_white", "")).strip()
            + ". Keep character marks and garment values target-locked."
        )
    lines = ["\nScene-aware rendering map:"]
    if not scoped_change or scope == "character":
        lines.append(
            "- Character: resolve "
            + str(character.get("resolve", "")).strip()
            + "; group "
            + str(character.get("group", "")).strip()
            + "; "
            + str(character.get("quiet", "")).strip()
            + "."
        )
    else:
        lines.append("- Character: keep the target's character rendering unchanged.")
    if not scoped_change or scope == "scene":
        lines.append(
            "- Depth: "
            + "; ".join(
                str(scene.get(field, "")).strip()
                for field in (
                    "focal_plane",
                    "near_plane",
                    "middle_plane",
                    "far_plane",
                    "paper_white",
                )
                if str(scene.get(field, "")).strip()
            )
            + "."
        )
    else:
        lines.append("- Scene: keep the target's scene rendering unchanged.")
    lines.append(
        "- Values: paper white for "
        + str(values.get("paper_white", "")).strip()
        + "; flat black for "
        + str(values.get("flat_black", "")).strip()
        + "; middle tone as "
        + str(values.get("middle_tone", "")).strip()
        + "."
    )
    return "\n".join(lines)


def compile_prompt(brief: dict[str, Any], manifest: dict[str, Any]) -> str:
    """Compile a bounded prompt whose detail level follows the task intent."""
    intent = task_intent(brief)
    medium = brief.get("medium", "manga")
    request = brief.get("request", "").strip()
    change = (brief.get("change_request") or request).strip()
    prompt_invariants = brief.get("prompt_invariants") or brief.get("invariants", [])
    invariants = [value for value in prompt_invariants if value]
    if invariants:
        invariant_lines = [f"- {value}" for value in invariants]
    elif (
        medium == "manga"
        and brief.get("change_category") in SCOPED_STYLE_CHANGE_CATEGORIES
    ):
        invariant_lines = [
            "- Preserve every already-correct identity, pose, composition, spatial relationship, named content, and the rendering domain outside brief.change_scope; replace only the declared rendering domain."
        ]
    else:
        invariant_lines = [
            "- Preserve every already-correct identity, composition, and rendering trait."
        ]
    reference_lines = _reference_lines(manifest)
    cross_medium_clause = _cross_medium_clause(manifest, medium)
    manga_finish_preservation = _manga_finish_preservation(medium)
    manga_medium_edit_clause = _manga_medium_edit_clause(
        medium,
        brief.get("change_category"),
        brief.get("change_scope"),
    )
    manga_wide_edit_lock = _manga_wide_edit_lock(
        medium, intent, brief.get("shot")
    )
    change_category = brief.get("change_category")
    change_scope = brief.get("change_scope")
    scoped_style_change = (
        intent in {"edit", "microfix"}
        and change_category in SCOPED_STYLE_CHANGE_CATEGORIES
        and change_scope in CHANGE_SCOPES
    )
    scene_economy_clause = (
        ""
        if scoped_style_change and change_scope == "character"
        else _scene_economy_clause(brief)
    )
    manga_finish_calibration = _manga_finish_calibration(
        medium,
        intent,
        manifest,
        change_category if scoped_style_change else None,
        change_scope if scoped_style_change else None,
    )
    character_style_mapping_clause = _character_style_mapping_clause(brief, manifest)
    contact_topology_clause = _contact_topology_clause(brief)
    dominant_material_clause = (
        ""
        if scoped_style_change and change_scope == "character"
        else _dominant_material_clause(brief)
    )
    rendering_map_clause = _rendering_map_clause(brief)
    preference_traits = brief.get("preference_traits") or []
    preference_line = (
        "\nLearned approved traits: " + ", ".join(preference_traits) + "."
        if preference_traits
        else ""
    )
    local_edit = brief.get("local_edit") or {}
    local_edit_line = ""
    if local_edit.get("mode") == "crop-composite":
        edit_box = local_edit.get("edit_box")
        context_box = local_edit.get("context_box")
        local_edit_line = (
            "\nInput 1 is a context crop, not the full canvas. Modify only the "
            f"requested area inside source edit box {edit_box}; context came from "
            f"source box {context_box}. Keep the crop boundary visually continuous "
            "so the edited center can be composited back into the untouched original.\n"
        )

    if intent == "microfix":
        category = brief.get("change_category") or "polish"
        text = f"""# Microfix specification

Edit the target image. Change only `{category}`: {change}
Change scope: `{brief.get("change_scope") or "target-only"}`.
{local_edit_line}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}
{rendering_map_clause}

Preserve exactly:
{chr(10).join(invariant_lines)}

Keep the current crop, pose, faces, expressions, character scale, line hierarchy, black-white balance, halftone density, background, and all non-target regions unchanged unless one is the named edit target. Produce one text-free {medium} image with no speech balloons, panel borders, signature, logo, or watermark. Do not redesign the whole image.{preference_line}
{manga_finish_preservation}
{manga_medium_edit_clause}
"""
    elif intent == "edit":
        construction_line = (
            "\nConstruction check: trace one continuous support or contact chain, keep "
            "occlusion order explicit, and reject floating, interpenetrating, or "
            "misaligned parts."
            if brief.get("change_category") == "construction"
            else ""
        )
        text = f"""# Edit specification

Requested edit: {change}
Selected medium: {medium}
Change scope: {brief.get("change_scope") or "target-only"}
{local_edit_line}

Identity requirements:
{chr(10).join(_identity_lines(brief))}

Canonical prop requirements:
{chr(10).join(_prop_lines(brief))}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}{character_style_mapping_clause}
{rendering_map_clause}

Preserve:
{chr(10).join(invariant_lines)}

Use the target as the exact continuity and composition authority. Change only what the request requires. Keep official references limited to identity, any selected-medium style screenshot limited to rendering, and content references limited to their exact focus. No unrequested text, balloons, borders, signature, logo, or watermark.{preference_line}
{construction_line}
{contact_topology_clause}
{manga_finish_preservation}
{manga_medium_edit_clause}
{manga_wide_edit_lock}
{dominant_material_clause}
{scene_economy_clause}
{manga_finish_calibration}
"""
    else:
        scene = brief.get("scene") or request
        aspect = brief.get("aspect_ratio") or "portrait"
        period = brief.get("period_mode") or "classic-balanced"
        shot = brief.get("shot")
        view_angle = brief.get("view_angle")
        construction = _medium_construction(medium, shot)
        deliverable = brief.get("deliverable", "illustration")
        if medium == "manga" and deliverable == "illustration":
            deliverable = (
                "single borderless serialized-manga panel, not a standalone illustration"
            )
        goal_line = f"Goal: {request}\n" if scene.strip() != request else ""
        text = f"""# Generation specification

{goal_line}Scene and exact moment: {scene}
Format: {aspect}; {deliverable}; {period}.
Camera distance: {shot or "unspecified"}; character view angle: {view_angle or "unspecified"}. Keep these as separate constraints.

Identity requirements:
{chr(10).join(_identity_lines(brief))}

Canonical prop requirements:
{chr(10).join(_prop_lines(brief))}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}{character_style_mapping_clause}

Priority order: requested scene and focal hierarchy first, official identity anchors second, selected-medium rendering third, and exact-focus content evidence fourth. Never blend the roles. Character-style evidence may affect only the character; scene-style evidence may affect only the environment and must never increase character detail density.

Composition: design a new composition from the request with one clear focal hierarchy. Do not copy a style screenshot's characters, dialogue, panel layout, pose, or story.

Spatial construction: use one coherent depth system; keep body direction, relative scale, overlap, ground contact, and prop attachment mechanically continuous.
{contact_topology_clause}

Medium construction: {construction}
{rendering_map_clause}
{dominant_material_clause}
{scene_economy_clause}
{manga_finish_calibration}

Required invariants:
{chr(10).join(invariant_lines)}

No unrequested lettering, speech balloons, panel borders, signature, logo, or watermark.{preference_line}
"""

    text = text.strip() + "\n"
    limit = prompt_limit(intent)
    if len(text) > limit:
        raise ValueError(
            f"Compiled {intent} prompt is {len(text)} characters; limit is {limit}"
        )
    return text


def write_compiled_prompt(task_dir: Path) -> Path:
    brief = read_json(task_dir / "brief.json")
    manifest = read_json(task_dir / "reference-manifest.json")
    profile_path = task_dir.parent.parent / "preference-profile.json"
    if profile_path.is_file():
        profile = read_json(profile_path)
        traits = profile.get(brief.get("medium", "manga"), {}).get("traits", [])
        brief["preference_traits"] = [
            row["tag"]
            for row in traits
            if row.get("count", 0) >= profile.get("minimum_support", 2)
        ][:5]
    output = task_dir / "prompt.md"
    atomic_write_text(output, compile_prompt(brief, manifest))
    return output


def reference_performance(tasks_root: Path) -> dict[str, dict[str, Any]]:
    """Aggregate append-only attempt outcomes without treating legacy acceptance as training data."""
    counts: dict[str, Counter[str]] = {}
    if not tasks_root.is_dir():
        return {}
    for attempt_path in tasks_root.glob("*/attempts/*/attempt.json"):
        if (attempt_path.parents[2] / "archived.json").is_file():
            continue
        try:
            attempt = read_json(attempt_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        status = attempt.get("status")
        if status not in {"accepted", "rejected"}:
            continue
        item_ids = attempt.get("reference_item_ids", [])
        if status == "rejected":
            # A failed image does not prove that every input reference was bad.
            # Only explicitly attributed reference failures may lower ranking.
            item_ids = attempt.get("reference_blame_item_ids", [])
        for item_id in item_ids:
            counts.setdefault(item_id, Counter())[status] += 1
    result = {}
    for item_id, counter in counts.items():
        accepted = counter["accepted"]
        rejected = counter["rejected"]
        total = accepted + rejected
        result[item_id] = {
            "accepted": accepted,
            "rejected": rejected,
            "total": total,
            "smoothed_acceptance": round((accepted + 1) / (total + 2), 4),
        }
    return result


def feedback_rank(stats: dict[str, Any] | None) -> float:
    """Return a conservative outcome score that stays near neutral with little data."""
    if not stats or not stats.get("total"):
        return 0.5
    confidence = stats["total"] / (stats["total"] + 3)
    return 0.5 + (stats["smoothed_acceptance"] - 0.5) * confidence
