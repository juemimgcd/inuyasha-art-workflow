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
            "flat black masses, and one restrained middle-tone family. Group repeated "
            "forms into larger shapes, let contours open or break when structure stays "
            "legible, and make detail fall away clearly from focal plane to distance. "
            "Apply the selected style anchor's same economy consistently across every "
            "scene material instead of completing each surface independently. "
            "Keep every canonical garment component, overlap, pattern, and accessory "
            "defined by official identity evidence, but render those same parts with "
            "the style reference's character contour, fabric and fold treatment, and "
            "relative paper-white, flat-black, and restrained middle-tone hierarchy. "
            "Never copy the style source's costume design or let its values redefine "
            "official garment construction."
        )
    return (
        "Make it read first as a late-1990s serialized black-and-white manga "
        "image, not a polished monochrome illustration or an under-rendered "
        "coloring-book outline. Match the selected style reference's "
        "scene-appropriate density band: use economical hand-inked shapes, "
        "decisive contour hierarchy, open white areas, flat black masses, and "
        "selective dot tone, while keeping every identity-bearing eye shape, "
        "bang division, jaw contour, hair silhouette, costume layer, and "
        "contact cue needed for recognition. Concentrate information at the "
        "face, hands, interaction, or action focus; let environment density "
        "follow the shot and narrative function. Avoid both strand-by-strand "
        "hair, abundant tiny folds, delicate micro-texture, smooth volume "
        "shading, glossy prestige-line-art refinement, and generic anime faces, "
        "uniform vector contours, empty architecture, or missing construction. "
        "Keep every canonical garment component, overlap, pattern, and accessory "
        "defined by official identity evidence, but render those same parts with the "
        "style reference's character contour, face, hair, fabric and fold treatment, "
        "and relative paper-white, flat-black, and restrained middle-tone hierarchy. "
        "Never copy the style source's costume design or let its values redefine "
        "official garment construction. Economy means selecting the right marks, not "
        "minimizing their count."
    )


def _manga_finish_preservation(medium: str) -> str:
    if medium != "manga":
        return ""
    return (
        "\nDo not drift toward extra digital polish or strip away "
        "identity-critical face, hair, costume, interaction, or setting cues."
    )


def _manga_medium_edit_clause(medium: str, change_category: str | None) -> str:
    if medium != "manga" or change_category != "medium":
        return ""
    return (
        "\nMedium replacement is the named edit. Preserve identity, pose, "
        "expression, composition, spatial relationships, and named content, but "
        "move the finish into the selected style reference's scene-appropriate "
        "density band. Remove redundant strands, folds, decorative texture, "
        "smooth shading, and nonfunctional background marks only where they "
        "exceed that band. Preserve identity-bearing eye and bang shapes, jaw, "
        "hair silhouette, costume construction, hand contact, and the setting "
        "cues required by the shot. Rebuild with open white paper, decisive flat "
        "blacks, selective dot tone, and tapered organic contour hierarchy. "
        "Merely changing gray to tone, or simplifying into generic sparse line "
        "art, both fail this edit. Do not impose numeric line, fold, strand, or "
        "rain-mark caps that are not evidenced by the selected style reference."
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
    elif medium == "manga" and brief.get("change_category") == "medium":
        invariant_lines = [
            "- Preserve every already-correct identity, pose, composition, spatial relationship, and named content; replace the current rendering finish."
        ]
    else:
        invariant_lines = [
            "- Preserve every already-correct identity, composition, and rendering trait."
        ]
    reference_lines = _reference_lines(manifest)
    cross_medium_clause = _cross_medium_clause(manifest, medium)
    manga_finish_preservation = _manga_finish_preservation(medium)
    manga_medium_edit_clause = _manga_medium_edit_clause(
        medium, brief.get("change_category")
    )
    manga_wide_edit_lock = _manga_wide_edit_lock(
        medium, intent, brief.get("shot")
    )
    dominant_material_clause = _dominant_material_clause(brief)
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
{manga_finish_preservation}
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

Canonical prop requirements:
{chr(10).join(_prop_lines(brief))}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}

Preserve:
{chr(10).join(invariant_lines)}

Use the target as the exact continuity and composition authority. Change only what the request requires. Keep official references limited to identity, any selected-medium style screenshot limited to rendering, and content references limited to their exact focus. No unrequested text, balloons, borders, signature, logo, or watermark.{preference_line}
{construction_line}
{manga_finish_preservation}
{manga_medium_edit_clause}
{manga_wide_edit_lock}
{dominant_material_clause}
"""
    else:
        scene = brief.get("scene") or request
        aspect = brief.get("aspect_ratio") or "portrait"
        period = brief.get("period_mode") or "classic-balanced"
        shot = brief.get("shot")
        construction = _medium_construction(medium, shot)
        deliverable = brief.get("deliverable", "illustration")
        if medium == "manga" and shot == "wide-shot":
            deliverable = (
                "single borderless serialized-manga panel, not a standalone illustration"
            )
        goal_line = f"Goal: {request}\n" if scene.strip() != request else ""
        text = f"""# Generation specification

{goal_line}Scene and exact moment: {scene}
Format: {aspect}; {deliverable}; {period}.

Identity requirements:
{chr(10).join(_identity_lines(brief))}

Canonical prop requirements:
{chr(10).join(_prop_lines(brief))}

Reference authority:
{chr(10).join(reference_lines)}{cross_medium_clause}

Priority order: requested scene and focal hierarchy first, official identity anchors second, selected-medium rendering third, and exact-focus content evidence fourth. Never blend the roles.

Composition: design a new composition from the request with one clear focal hierarchy. Do not copy a style screenshot's characters, dialogue, panel layout, pose, or story.

Spatial construction: use one coherent depth system; keep body direction, relative scale, overlap, ground contact, and prop attachment mechanically continuous.

Medium construction: {construction}
{dominant_material_clause}

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
