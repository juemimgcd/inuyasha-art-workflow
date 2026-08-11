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
ATTEMPT_SCHEMA_VERSION = 1
LATENCY_SCHEMA_VERSION = 2
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


def prompt_limit(intent: str) -> int:
    return {"new": 7000, "edit": 3500, "microfix": 1800}[intent]


def _reference_lines(manifest: dict[str, Any]) -> list[str]:
    lines = []
    for index, entry in enumerate(manifest.get("references", []), 1):
        role = entry.get("role", "unknown")
        instruction = entry.get("instructions") or "Use only for its declared role."
        lines.append(f"- Input {index} ({role}): {instruction}")
    return lines or ["- No references prepared yet."]


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


def _identity_lines(brief: dict[str, Any]) -> list[str]:
    forms = brief.get("identity_forms") or {}
    costumes = brief.get("forms_and_costumes") or []
    ledgers = {}
    if IDENTITY_LEDGERS_PATH.is_file():
        ledgers = read_json(IDENTITY_LEDGERS_PATH).get("characters", {})
    lines = []
    for name, form in forms.items():
        profile = ledgers.get(name, {})
        details = [
            *profile.get("common", []),
            *profile.get("forms", {}).get(form, []),
            *profile.get("exclusions", []),
        ]
        suffix = "；".join(details) if details else f"required form `{form}`"
        lines.append(f"- {name} ({form}): {suffix}")
    default_costumes = {f"{name}: {form}" for name, form in forms.items()}
    lines.extend(
        f"- {value}" for value in costumes if value and value not in default_costumes
    )
    return lines or ["- No named focal character."]


def compile_prompt(brief: dict[str, Any], manifest: dict[str, Any]) -> str:
    """Compile a bounded prompt whose detail level follows the task intent."""
    intent = task_intent(brief)
    medium = brief.get("medium", "manga")
    request = brief.get("request", "").strip()
    change = (brief.get("change_request") or request).strip()
    prompt_invariants = brief.get("prompt_invariants") or brief.get("invariants", [])
    invariants = [value for value in prompt_invariants if value]
    invariant_lines = [f"- {value}" for value in invariants] or [
        "- Preserve every already-correct identity, composition, and rendering trait."
    ]
    reference_lines = _reference_lines(manifest)
    cross_medium_clause = _cross_medium_clause(manifest, medium)
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
{local_edit_line}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}

Preserve exactly:
{chr(10).join(invariant_lines)}

Keep the current crop, pose, faces, expressions, character scale, line hierarchy, black-white balance, halftone density, background, and all non-target regions unchanged unless one is the named edit target. Produce one text-free {medium} image with no speech balloons, panel borders, signature, logo, or watermark. Do not redesign the whole image.{preference_line}
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
{local_edit_line}

Identity requirements:
{chr(10).join(_identity_lines(brief))}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}

Preserve:
{chr(10).join(invariant_lines)}

Use the target as the exact continuity and composition authority. Change only what the request requires. Keep official references limited to identity, selected-medium style screenshots limited to rendering, and content references limited to their exact focus. No unrequested text, balloons, borders, signature, logo, or watermark.{preference_line}
{construction_line}
"""
    else:
        scene = brief.get("scene") or request
        aspect = brief.get("aspect_ratio") or "portrait"
        period = brief.get("period_mode") or "classic-balanced"
        construction = (
            "Use flexible tapered dip-pen contours, clean white skin, decisive black "
            "masses, restrained halftone, one dense texture zone, and a readable focal silhouette."
            if medium == "manga"
            else "Use the selected medium's inspected rendering grammar."
        )
        goal_line = f"Goal: {request}\n" if scene.strip() != request else ""
        text = f"""# Generation specification

{goal_line}Scene and exact moment: {scene}
Format: {aspect}; {brief.get("deliverable", "illustration")}; {period}.

Identity requirements:
{chr(10).join(_identity_lines(brief))}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}

Priority order: requested scene and focal hierarchy first, official identity anchors second, selected-medium rendering third, and exact-focus content evidence fourth. Never blend the roles.

Composition: design a new composition from the request with one clear focal hierarchy. Do not copy a style screenshot's characters, dialogue, panel layout, pose, or story.

Spatial construction: use one coherent depth system; keep body direction, relative scale, overlap, ground contact, and prop attachment mechanically continuous.

Medium construction: {construction}

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
