"""Reference-role ordering, authority, and prompt-instruction policy."""

from __future__ import annotations

import json

ALLOWED_ROLES = {
    "target",
    "style",
    "identity",
    "form",
    "composition",
    "continuity",
    "content",
}
ROLE_ORDER = {
    "target": 0,
    "style": 1,
    "identity": 2,
    "form": 3,
    "continuity": 4,
    "composition": 5,
    "content": 6,
}
MANGA_STYLE_INSTRUCTION = (
    "Control only black-and-white manga mark-making: line hierarchy, black-white "
    "massing, halftone economy, facial simplification, effect construction, "
    "background omission, material simplification, negative space, and "
    "distance-based detail falloff. "
    "Do not copy visible characters, dialogue, balloons, panel borders, layout, or story content."
)
TV_STYLE_INSTRUCTION = (
    "Control only TV rendering: palette, clean animation contours, cel-shadow depth, "
    "lighting, and background treatment. Do not override official character identity "
    "or copy the source shot's story and composition."
)
IDENTITY_INSTRUCTION = (
    "Control canonical character identity, form, anatomy, costume, weapon or prop "
    "construction, attachment, and scale only. Do not control rendering style or "
    "scene composition."
)
FORM_INSTRUCTION = (
    "Control only the exact requested form or age state visible in this selected-medium "
    "original: age-specific proportions, silhouette, face construction, hair-to-ear "
    "relationship, and form-specific garment scale. Do not control general character "
    "identity beyond visible form evidence, rendering style, palette, scene composition, "
    "or story content."
)
CONTINUITY_INSTRUCTION = (
    "Control only the user's selected visual continuity and proven finish quality. "
    "Do not override official identity, the selected medium's rendering grammar, or the new composition."
)
CONTENT_INSTRUCTION = (
    "Control only the exact visible content named by Exact focus: the requested "
    "action state, object or creature configuration, effect phase, or necessary "
    "spatial relationship. Do not control named-character identity, form, costume, "
    "palette, rendering style, camera framing, background treatment, or story staging."
)


def instruction_for(
    role: str,
    medium: str,
    crop_box: tuple[int, int, int, int] | None = None,
    focus: str = "",
    source_medium: str | None = None,
    content_provenance: str = "observed-content",
) -> str:
    instructions = {
        "identity": IDENTITY_INSTRUCTION,
        "form": FORM_INSTRUCTION,
        "style": MANGA_STYLE_INSTRUCTION if medium == "manga" else TV_STYLE_INSTRUCTION,
        "continuity": CONTINUITY_INSTRUCTION,
    }
    instruction = instructions.get(role, "")
    if role == "content":
        if not focus:
            raise ValueError("Content references require an exact focus")
        instruction = CONTENT_INSTRUCTION
        if source_medium and source_medium != medium:
            instruction += (
                f" This is cross-medium {source_medium}-to-{medium} content evidence. "
                f"Ignore all {source_medium} palette, contour, shading, texture, and "
                f"background grammar; translate only the named content into the {medium} "
                "rendering established by the style reference."
            )
        if content_provenance == "fallback-medium-original":
            if not source_medium or source_medium == medium:
                raise ValueError(
                    "fallback-medium-original provenance requires cross-medium content"
                )
            instruction += (
                " This design is explicitly original to the fallback medium; label "
                "the result as a source-medium-derived adaptation and do not present "
                "it as selected-medium canonical evidence."
            )
    if crop_box is not None:
        instruction += (
            f" This prepared image is a task-local crop {crop_box} from the recorded "
            "source; use only construction visible inside the crop and do not infer "
            "omitted states."
        )
    if focus:
        instruction += f" Exact focus: {focus}"
    return instruction.strip()


def _json_values(row, field: str) -> set[str]:
    return set(json.loads(row[field] or "[]"))


def _json_object(row, field: str) -> dict[str, list[str]]:
    if hasattr(row, "keys") and field not in row:
        return {}
    return json.loads(row[field] or "{}")


def validate_reference(
    row,
    role: str,
    item_id: str,
    medium: str,
    identity_forms: dict[str, str],
    *,
    crop_box: tuple[int, int, int, int] | None = None,
    focus: str = "",
) -> None:
    if role not in ALLOWED_ROLES:
        raise SystemExit(f"Unknown reference role in manifest: {role}")

    source_id = row["source_id"]
    required_role = {"style": "rendering", "form": "rendering"}.get(role, role)
    has_eligible_roles = hasattr(row, "keys") and "eligible_roles" in row
    eligible_roles = _json_values(row, "eligible_roles") if has_eligible_roles else set()
    if has_eligible_roles and required_role not in eligible_roles:
        raise SystemExit(
            f"Reference is not eligible for role {role}: {item_id}; "
            f"eligible roles={sorted(eligible_roles)}"
        )
    expected_medium_source = "manga-curated" if medium == "manga" else "tv-curated"
    source_rules = {
        "identity": (
            {"official"},
            "Identity references must come from official setting sheets",
        ),
        "form": (
            {expected_medium_source},
            f"{medium} form references must come from {expected_medium_source}",
        ),
        "style": (
            {expected_medium_source},
            f"{medium} style references must come from {expected_medium_source}",
        ),
        "target": (
            {"user-continuity"},
            "Target references must come from user-continuity",
        ),
        "continuity": (
            {"selected-output", "user-continuity"},
            "Continuity references must come from selected-output or user-continuity",
        ),
        "composition": (
            {"user-continuity"},
            "Composition references must be user-supplied",
        ),
        "content": (
            {"manga-curated", "tv-curated"},
            "Content references must come from manga-curated or tv-curated",
        ),
    }
    allowed_sources, error = source_rules[role]
    if source_id not in allowed_sources:
        raise SystemExit(f"{error}: {item_id}")

    # Style evidence controls mark-making only. Visible characters or forms in
    # that screenshot must not become an identity gate for the target task.
    if role == "style":
        return
    if not identity_forms:
        return
    subjects = _json_values(row, "subjects")
    forms = _json_values(row, "forms")
    subject_forms = _json_object(row, "subject_forms")
    matching_subjects = subjects & set(identity_forms)
    if role in {"identity", "form"} and not matching_subjects:
        raise SystemExit(
            f"{role.title()} reference does not name any requested character: "
            f"{item_id}; indexed subjects={sorted(subjects) or ['unclassified']}"
        )
    for subject in sorted(matching_subjects):
        required_form = identity_forms[subject]
        compatible_forms = set(subject_forms.get(subject, [])) or forms
        if required_form not in compatible_forms:
            if role == "content" and crop_box is not None and focus.strip():
                continue
            indexed = sorted(compatible_forms) or ["unclassified"]
            raise SystemExit(
                "Form-incompatible reference rejected: "
                f"{item_id} depicts {subject} as {indexed}, "
                f"but this task requires {required_form}"
            )


def validate_reference_order(references: list[tuple[str, str]]) -> None:
    roles = [role for role, _ in references]
    limits = {
        "target": "Use at most one target reference",
        "continuity": "Use at most one selected-output continuity reference",
        "content": "Use at most one exact-focus content reference",
    }
    for role, error in limits.items():
        if roles.count(role) > 1:
            raise SystemExit(error)
    if "target" in roles and roles[0] != "target":
        raise SystemExit("A target reference must be first")
    ranks = [ROLE_ORDER[role] for role in roles]
    if ranks != sorted(ranks):
        raise SystemExit(
            "Reference order must be target, style, identity, form, continuity, composition, content"
        )


def ordered_reference_additions(
    existing: list[tuple[str, str]], additions: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Order only new entries without hiding an invalid existing manifest."""
    validate_reference_order(existing)
    ordered = [*existing, *sorted(additions, key=lambda item: ROLE_ORDER[item[0]])]
    validate_reference_order(ordered)
    return ordered
