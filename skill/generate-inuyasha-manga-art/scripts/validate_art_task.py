#!/usr/bin/env python3
"""Validate one art task before generation or final acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_reference_index import freshness
from composite_local_microfix import outside_edit_box_equal
from prepare_reference_set import (
    image_pixel_hash,
    source_crop_pixel_hash,
    validate_crop_box,
    validate_reference,
    validate_reference_order,
)
from task_workflow import (
    BRIEF_SCHEMA_VERSION,
    CHANGE_CATEGORIES,
    DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS,
    DEFAULT_MAX_TECHNICAL_RETRIES,
    DEFAULT_POST_GENERATION_TARGET_SECONDS,
    INTENT_VALUES,
    RESULT_SCHEMA_VERSION,
    elapsed_seconds,
    latency_budget,
    parse_timestamp,
    prompt_limit,
    task_intent,
)
from workflow_common import (
    library_signature,
    load_config,
    now_iso,
    open_database,
    resolve_recorded_path,
    workflow_paths,
    workflow_root,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument(
        "--stage", choices=("pre-generation", "final"), default="pre-generation"
    )
    return parser.parse_args()


def load_json(path: Path, failures: list[str]) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read {path.name}: {exc}")
        return {}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crop_derives_from_source(
    source: Path, rendered: Path, crop_box: tuple[int, int, int, int]
) -> bool:
    return image_pixel_hash(rendered) == source_crop_pixel_hash(source, crop_box)


def output_path(result: dict) -> Path | None:
    for key in ("output", "task_output", "accepted_output"):
        if result.get(key):
            return resolve_recorded_path(result[key])
    return None


def candidate_source_failures(
    task_dir: Path, brief: dict, references: list[dict]
) -> list[str]:
    """Verify that a candidate-edit target derives from one recorded attempt."""
    source = brief.get("candidate_source")
    if not source:
        return []
    failures = []
    if brief.get("intent") != "edit":
        failures.append("candidate_source is valid only for edit tasks")
    task_id = source.get("task_id")
    attempt_number = source.get("attempt")
    if not task_id or brief.get("parent_task_id") != task_id:
        failures.append("candidate_source.task_id must match brief.parent_task_id")
        return failures
    if not isinstance(attempt_number, int) or attempt_number < 1:
        failures.append("candidate_source.attempt must be a positive integer")
        return failures
    parent = task_dir.parent / task_id
    attempt_path = parent / "attempts" / f"{attempt_number:03d}" / "attempt.json"
    if not attempt_path.is_file():
        failures.append(f"candidate source attempt is missing: {attempt_path}")
        return failures
    attempt = load_json(attempt_path, failures)
    if attempt.get("status") not in {"accepted", "rejected"}:
        failures.append("candidate source attempt must contain an image output")
    output_text = attempt.get("output")
    output = resolve_recorded_path(output_text) if output_text else None
    if output is None or not output.is_file():
        failures.append("candidate source output is missing")
        return failures
    output_hash = file_hash(output)
    if attempt.get("attempt") != attempt_number:
        failures.append("candidate source attempt number does not match its directory")
    if source.get("status") != attempt.get("status"):
        failures.append("brief.candidate_source status does not match attempt.json")
    if resolve_recorded_path(source.get("output", "")) != output:
        failures.append("brief.candidate_source output does not match attempt.json")
    if attempt.get("output_sha256") != output_hash:
        failures.append("candidate source output hash changed after attempt recording")
    if source.get("output_sha256") != output_hash:
        failures.append("brief.candidate_source output hash is incorrect")
    target = references[0] if references else {}
    if target.get("role") != "target":
        failures.append("candidate edit must place its source attempt target first")
    else:
        original = resolve_recorded_path(target.get("original_path", ""))
        if original != output:
            failures.append(
                "candidate edit target does not match the source attempt output"
            )
        if target.get("content_hash") != output_hash:
            failures.append(
                "candidate edit target hash does not match the source attempt"
            )
        if target.get("source_attempt") != source:
            failures.append(
                "candidate edit target is missing exact source_attempt provenance"
            )
    local_edit = brief.get("local_edit") or {}
    if local_edit.get("mode") != "crop-composite":
        failures.append("candidate edits require crop-composite local_edit metadata")
    elif resolve_recorded_path(local_edit.get("target", "")) != output:
        failures.append("candidate local_edit target does not match the source attempt")
    return failures


def unchanged_consecutive_errors(task_dir: Path) -> int:
    current_files = [task_dir / "prompt.md", task_dir / "reference-manifest.json"]
    if not all(path.is_file() for path in current_files):
        return 0
    count = 0
    for attempt_path in sorted(
        (task_dir / "attempts").glob("*/attempt.json"), reverse=True
    ):
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        if attempt.get("status") != "error":
            break
        snapshot_dir = attempt_path.parent
        snapshots = [snapshot_dir / path.name for path in current_files]
        if not all(path.is_file() for path in snapshots):
            break
        if any(
            file_hash(current) != file_hash(snapshot)
            for current, snapshot in zip(current_files, snapshots)
        ):
            break
        count += 1
    return count


def consecutive_technical_errors(
    task_dir: Path, response_started_at: str | None = None
) -> int:
    """Count the latest uninterrupted run of recorded technical failures.

    A changed prompt or manifest does not reset a transport/backend failure streak.
    The workflow contract allows one meaningful retry, then requires a handoff
    instead of spending more image-generation calls in the same task.
    """
    count = 0
    for attempt_path in sorted(
        (task_dir / "attempts").glob("*/attempt.json"), reverse=True
    ):
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        if (
            response_started_at is not None
            and attempt.get("response_started_at") != response_started_at
        ):
            break
        categories = {
            failure.get("category")
            for failure in attempt.get("failures", [])
            if isinstance(failure, dict)
        }
        if attempt.get("status") != "error" or "technical" not in categories:
            break
        count += 1
    return count


def retrieval_result(evidence: str, label: str) -> str:
    match = re.search(
        rf"^- {re.escape(label)}:\s*`?(HIT|MISS|INSUFFICIENT|SKIP)`?\s*$",
        evidence,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else ""


def technical_retry_limit_reached(
    technical_error_streak: int, max_technical_retries: int
) -> bool:
    """Return whether the initial call plus configured retries were consumed."""
    return technical_error_streak > max_technical_retries


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    warnings: list[str] = []
    latency_result: dict = {}
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    paths = workflow_paths(root)
    task_dir = args.task_dir.expanduser().resolve()
    tasks_root = paths["tasks"].resolve()
    if task_dir.parent != tasks_root:
        failures.append(f"task must be directly under {tasks_root}")
    archived_path = task_dir / "archived.json"
    if archived_path.is_file():
        archived = load_json(archived_path, failures)
        failures.append(
            f"task is archived: {archived.get('reason') or 'no reason recorded'}"
        )

    required = [
        "brief.json",
        "evidence-log.md",
        "reference-manifest.json",
        "prompt.md",
        "qa.json",
    ]
    if args.stage == "final":
        required.append("result.json")
    for name in required:
        if not (task_dir / name).is_file():
            failures.append(f"missing task file: {name}")
    if failures:
        print(
            json.dumps(
                {"ok": False, "stage": args.stage, "failures": failures},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    fresh, reason = freshness(
        paths["database"], config, library_signature(config), paths["annotations"]
    )
    if not fresh:
        failures.append(f"catalog is stale: {reason}")

    brief = load_json(task_dir / "brief.json", failures)
    manifest = load_json(task_dir / "reference-manifest.json", failures)
    brief_schema = brief.get("schema_version", 0)
    if brief_schema < 4:
        failures.append("brief schema is legacy; migrate or archive this task")
    raw_intent = brief.get("intent")
    intent = task_intent(brief)
    if brief_schema >= BRIEF_SCHEMA_VERSION and raw_intent not in INTENT_VALUES:
        failures.append(f"brief.intent must be one of: {', '.join(INTENT_VALUES)}")
    if intent == "microfix":
        if not brief.get("parent_task_id"):
            failures.append("microfix tasks require brief.parent_task_id")
        if brief.get("change_category") not in CHANGE_CATEGORIES:
            failures.append("microfix tasks require a supported change_category")
        if not brief.get("change_request"):
            failures.append("microfix tasks require brief.change_request")
    for field in ("request", "scene", "aspect_ratio"):
        if not brief.get(field):
            failures.append(f"brief.{field} is required")
    if not brief.get("invariants"):
        failures.append("brief.invariants must not be empty")
    try:
        budget = latency_budget(brief)
        if budget["pre_generation_target_seconds"] < 1:
            failures.append("pre-generation target must be a positive integer")
        if budget["post_generation_target_seconds"] < 1:
            failures.append("post-generation target must be a positive integer")
        if budget["max_technical_retries"] < 0:
            failures.append("max technical retries cannot be negative")
    except (TypeError, ValueError):
        budget = {
            "pre_generation_target_seconds": DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS,
            "post_generation_target_seconds": DEFAULT_POST_GENERATION_TARGET_SECONDS,
            "max_technical_retries": DEFAULT_MAX_TECHNICAL_RETRIES,
        }
        failures.append("brief.latency_budget contains invalid values")
    medium = brief.get("medium")
    if medium not in {"manga", "tv"}:
        failures.append("brief.medium must be manga or tv")
    identity_forms = brief.get("identity_forms") or {}
    characters = brief.get("characters") or []
    if set(characters) != set(identity_forms):
        failures.append(
            "brief.characters and identity_forms must name the same characters"
        )

    evidence = (task_dir / "evidence-log.md").read_text(encoding="utf-8")
    if re.search(r"^- [^:\n]+:\s*$", evidence, flags=re.MULTILINE):
        failures.append("evidence-log.md still contains blank template fields")
    prompt = (task_dir / "prompt.md").read_text(encoding="utf-8")
    if (
        "canonical name | form/age" in prompt
        or "Fill from `reference-manifest.json`" in prompt
    ):
        failures.append("prompt.md still contains template instructions")
    if len(prompt) > prompt_limit(intent):
        failures.append(f"{intent} prompt exceeds {prompt_limit(intent)} characters")
    if args.stage == "pre-generation":
        response_window_path = task_dir / "response-window.json"
        response_started_at = None
        pre_generation_elapsed = None
        response_window = {}
        if response_window_path.is_file():
            response_window = load_json(response_window_path, failures)
            response_started_at = response_window.get(
                "pre_generation_started_at"
            ) or response_window.get("started_at")
            try:
                parse_timestamp(response_started_at)
                pre_generation_elapsed = elapsed_seconds(response_started_at, now_iso())
            except (TypeError, ValueError) as exc:
                failures.append(f"invalid response-window.json: {exc}")
        if pre_generation_elapsed is not None:
            pre_target = int(
                response_window.get("pre_generation_target_seconds")
                or budget["pre_generation_target_seconds"]
            )
            latency_result = {
                "pre_generation_started_at": response_started_at,
                "pre_generation_elapsed_seconds": pre_generation_elapsed,
                "pre_generation_target_seconds": pre_target,
                "pre_generation_target_met": pre_generation_elapsed <= pre_target,
                "generation_latency_policy": "observe-only",
                "post_generation_target_seconds": budget[
                    "post_generation_target_seconds"
                ],
            }
            if pre_generation_elapsed > pre_target:
                warnings.append(
                    "pre-generation soft target exceeded; make the image call now and "
                    "defer non-blocking bookkeeping until after the first preview"
                )

        technical_error_streak = consecutive_technical_errors(
            task_dir, response_started_at
        )
        if technical_retry_limit_reached(
            technical_error_streak, budget["max_technical_retries"]
        ):
            failures.append(
                "retry stop: the configured number of consecutive technical retries "
                "was already used in this response window"
            )
        elif (
            response_started_at is None
            and unchanged_consecutive_errors(task_dir) > budget["max_technical_retries"]
        ):
            failures.append(
                "retry stop: two consecutive errors used the unchanged prompt and "
                "reference manifest; change the failing condition before generating again"
            )

    references = manifest.get("references") or []
    failures.extend(candidate_source_failures(task_dir, brief, references))
    if not references:
        failures.append("reference manifest is empty")
    reference_limit = 5 if intent == "microfix" else 6
    if len(references) > reference_limit:
        failures.append(
            f"reference manifest contains more than {reference_limit} images"
        )

    connection = open_database(paths["database"], read_only=True)
    resolved = []
    seen = set()
    identity_coverage = set()
    form_coverage = set()
    for expected_order, entry in enumerate(references, 1):
        item_id = entry.get("item_id", "")
        role = entry.get("role", "")
        if entry.get("order") != expected_order:
            failures.append(
                f"manifest order is not sequential at {item_id or expected_order}"
            )
        rendered = resolve_recorded_path(entry.get("rendered_path", ""))
        if entry.get("source_id") == "user-supplied":
            if role not in {"target", "composition"}:
                failures.append(f"unsupported user-supplied role: {role}")
            if not rendered.is_file():
                failures.append(f"prepared reference is missing: {rendered}")
            else:
                crop_box = entry.get("crop_box")
                if crop_box is None:
                    transport = entry.get("transport")
                    if transport:
                        source = resolve_recorded_path(entry.get("original_path", ""))
                        try:
                            if not isinstance(transport, dict):
                                raise ValueError("transport must be an object")
                            if not source.is_file():
                                raise ValueError(
                                    f"external transport source is missing: {source}"
                                )
                            if file_hash(source) != entry.get("content_hash"):
                                failures.append(
                                    f"external transport source content changed: {source}"
                                )
                            if transport.get("kind") != "downscaled-jpeg":
                                failures.append(
                                    f"unsupported external target transport: {item_id}"
                                )
                            if file_hash(rendered) != transport.get(
                                "rendered_content_hash"
                            ):
                                failures.append(
                                    f"prepared transport content changed: {rendered}"
                                )
                            from PIL import Image

                            with Image.open(source) as source_image:
                                source_dimensions = [
                                    source_image.width,
                                    source_image.height,
                                ]
                            with Image.open(rendered) as rendered_image:
                                rendered_dimensions = [
                                    rendered_image.width,
                                    rendered_image.height,
                                ]
                            if source_dimensions != transport.get("source_dimensions"):
                                failures.append(
                                    f"external transport source dimensions changed: {source}"
                                )
                            if rendered_dimensions != transport.get(
                                "rendered_dimensions"
                            ):
                                failures.append(
                                    f"external transport dimensions changed: {rendered}"
                                )
                            max_edge = transport.get("max_edge")
                            if not isinstance(max_edge, int) or max_edge < 256:
                                failures.append(
                                    f"invalid external transport max edge: {item_id}"
                                )
                            elif max(rendered_dimensions) > max_edge:
                                failures.append(
                                    f"external transport exceeds max edge: {rendered}"
                                )
                            quality = transport.get("quality")
                            if (
                                not isinstance(quality, int)
                                or quality < 1
                                or quality > 95
                            ):
                                failures.append(
                                    f"invalid external transport JPEG quality: {item_id}"
                                )
                        except (OSError, TypeError, ValueError) as exc:
                            failures.append(
                                f"invalid external target transport for {item_id}: {exc}"
                            )
                    elif file_hash(rendered) != entry.get("content_hash"):
                        failures.append(
                            f"prepared reference content changed: {rendered}"
                        )
                else:
                    source = resolve_recorded_path(entry.get("original_path", ""))
                    normalized_crop = None
                    try:
                        normalized_crop = tuple(crop_box)
                        if len(normalized_crop) != 4 or not all(
                            isinstance(value, int) for value in normalized_crop
                        ):
                            raise ValueError("crop_box must contain four integers")
                        if not source.is_file():
                            raise ValueError(
                                f"external crop source is missing: {source}"
                            )
                        from PIL import Image

                        with Image.open(source) as source_image:
                            validate_crop_box(normalized_crop, source_image.size)
                        if file_hash(source) != entry.get("content_hash"):
                            failures.append(
                                f"external target source content changed: {source}"
                            )
                        if not entry.get("focus"):
                            failures.append(
                                f"cropped target has no exact focus: {item_id}"
                            )
                        if file_hash(rendered) != entry.get("rendered_content_hash"):
                            failures.append(
                                f"prepared target crop content changed: {rendered}"
                            )
                        expected_crop_hash = source_crop_pixel_hash(
                            source, normalized_crop
                        )
                        if expected_crop_hash != entry.get("crop_source_hash"):
                            failures.append(
                                f"prepared target crop does not derive from source: {rendered}"
                            )
                        if not crop_derives_from_source(
                            source, rendered, normalized_crop
                        ):
                            failures.append(
                                f"prepared target crop pixels differ from source: {rendered}"
                            )
                    except (OSError, TypeError, ValueError) as exc:
                        failures.append(f"invalid target crop for {item_id}: {exc}")
            if item_id in seen:
                failures.append(f"duplicate reference item: {item_id}")
            seen.add(item_id)
            resolved.append((role, item_id))
            continue

        row = connection.execute(
            """
            SELECT items.*, sources.authority, sources.medium
            FROM items JOIN sources ON sources.source_id = items.source_id
            WHERE items.item_id = ? OR items.item_id = (
                SELECT item_id FROM item_aliases WHERE alias_id = ?
            )
            """,
            (item_id, item_id),
        ).fetchone()
        if row is None:
            failures.append(f"unknown catalog item: {item_id or '[missing]'}")
            continue
        if row["item_id"] in seen:
            failures.append(f"duplicate catalog item: {item_id}")
            continue
        seen.add(row["item_id"])
        try:
            validate_reference(row, role, item_id, medium, identity_forms)
        except SystemExit as exc:
            failures.append(str(exc))
        resolved.append((role, row["item_id"]))
        if role == "identity":
            identity_coverage.update(json.loads(row["subjects"] or "[]"))
        if role == "form":
            form_coverage.update(json.loads(row["subjects"] or "[]"))
        if entry.get("content_hash") != row["content_hash"]:
            failures.append(f"catalog hash mismatch: {item_id}")
        if role == "content":
            focus = (entry.get("focus") or "").strip()
            planned_focus = (brief.get("content_need") or {}).get("focus")
            if not focus:
                failures.append(f"content reference has no exact focus: {item_id}")
            if not planned_focus:
                failures.append(
                    "content reference was not declared in brief.content_need"
                )
            elif focus != planned_focus:
                failures.append(
                    f"content focus does not match brief.content_need: {item_id}"
                )
            expected_cross_medium = row["medium"] != medium
            if entry.get("evidence_medium") != row["medium"]:
                failures.append(f"content evidence medium is wrong: {item_id}")
            if entry.get("cross_medium") is not expected_cross_medium:
                failures.append(f"content cross_medium marker is wrong: {item_id}")
            expected_conversion = (
                f"{row['medium']}-to-{medium}-content"
                if expected_cross_medium
                else None
            )
            if entry.get("conversion") != expected_conversion:
                failures.append(f"content conversion marker is wrong: {item_id}")
            expected_provenance = (brief.get("content_need") or {}).get(
                "provenance", "observed-content"
            )
            if entry.get("provenance") != expected_provenance:
                failures.append(f"content provenance marker is wrong: {item_id}")
            if (
                expected_provenance == "fallback-medium-original"
                and not expected_cross_medium
            ):
                failures.append(
                    "fallback-medium-original provenance requires cross-medium content"
                )
            instructions = entry.get("instructions") or ""
            if (
                "Control only the exact visible content named by Exact focus"
                not in instructions
            ):
                failures.append(f"content authority instruction is missing: {item_id}")
            if expected_cross_medium and "This is cross-medium" not in instructions:
                failures.append(
                    f"cross-medium conversion instruction is missing: {item_id}"
                )
            if (
                expected_provenance == "fallback-medium-original"
                and "do not present it as selected-medium canonical evidence"
                not in instructions
            ):
                failures.append(
                    f"fallback-original provenance instruction is missing: {item_id}"
                )
        if not rendered.is_file():
            failures.append(f"prepared reference is missing: {rendered}")
        else:
            crop_box = entry.get("crop_box")
            if crop_box is not None:
                normalized_crop = None
                try:
                    normalized_crop = tuple(crop_box)
                    if len(normalized_crop) != 4 or not all(
                        isinstance(value, int) for value in normalized_crop
                    ):
                        raise ValueError("crop_box must contain four integers")
                    validate_crop_box(normalized_crop, (row["width"], row["height"]))
                except (TypeError, ValueError) as exc:
                    failures.append(f"invalid crop for {item_id}: {exc}")
                if not entry.get("focus"):
                    failures.append(f"cropped reference has no exact focus: {item_id}")
                expected_rendered_hash = entry.get("rendered_content_hash")
                if not expected_rendered_hash:
                    failures.append(
                        f"cropped reference has no rendered hash: {item_id}"
                    )
                elif file_hash(rendered) != expected_rendered_hash:
                    failures.append(f"prepared crop content changed: {rendered}")
                if normalized_crop is not None and row["kind"] == "image":
                    try:
                        expected_crop_hash = source_crop_pixel_hash(
                            Path(row["path"]), normalized_crop
                        )
                        if not crop_derives_from_source(
                            Path(row["path"]), rendered, normalized_crop
                        ):
                            failures.append(
                                f"prepared crop does not derive from catalog source: {rendered}"
                            )
                        recorded_source_hash = entry.get("crop_source_hash")
                        if (
                            recorded_source_hash
                            and recorded_source_hash != expected_crop_hash
                        ):
                            failures.append(
                                f"recorded crop source hash is wrong: {item_id}"
                            )
                    except (OSError, ValueError) as exc:
                        failures.append(
                            f"cannot verify crop source for {item_id}: {exc}"
                        )
            elif row["kind"] == "image" and file_hash(rendered) != row["content_hash"]:
                failures.append(f"prepared reference content changed: {rendered}")
    connection.close()

    try:
        validate_reference_order(resolved)
    except (KeyError, SystemExit) as exc:
        failures.append(str(exc))
    style_count = sum(role == "style" for role, _ in resolved)
    target_count = sum(role == "target" for role, _ in resolved)
    if intent == "new" and style_count not in {1, 2}:
        failures.append("new tasks require one or two selected-medium style references")
    if intent in {"edit", "microfix"} and style_count > 1:
        failures.append(f"{intent} tasks may use at most one style reference")
    if intent in {"edit", "microfix"} and target_count != 1:
        failures.append(f"{intent} tasks require exactly one target reference")
    missing_identity = set(characters) - (identity_coverage | form_coverage)
    identity_required = intent == "new" or brief.get("change_category") in {
        "identity",
        "form",
        "costume",
        "anatomy",
        "construction",
    }
    if identity_required and missing_identity:
        failures.append(
            "missing official identity or selected-medium exact-form coverage: "
            f"{sorted(missing_identity)}"
        )
    if form_coverage:
        official_section = evidence.split("## Layer 2:", 1)[0]
        if not re.search(
            r"^- Result:\s*`?(?:MISS|INSUFFICIENT)`?\s*$",
            official_section,
            flags=re.MULTILINE,
        ):
            failures.append(
                "selected-medium form fallback requires official identity MISS or INSUFFICIENT"
            )
    manifest_styles = [item_id for role, item_id in resolved if role == "style"]
    if brief.get("style_references") != manifest_styles:
        failures.append("brief.style_references does not match the manifest")
    manifest_forms = [item_id for role, item_id in resolved if role == "form"]
    if (brief.get("form_references") or []) != manifest_forms:
        failures.append("brief.form_references does not match the manifest")
    manifest_contents = [item_id for role, item_id in resolved if role == "content"]
    if (brief.get("content_references") or []) != manifest_contents:
        failures.append("brief.content_references does not match the manifest")
    if manifest_contents:
        content_entry = next(
            entry for entry in references if entry.get("role") == "content"
        )
        planned_focus = (brief.get("content_need") or {}).get("focus") or ""
        if planned_focus and planned_focus not in prompt:
            failures.append("compiled prompt does not name the exact content focus")
        if (
            content_entry.get("cross_medium")
            and "Cross-medium content conversion" not in prompt
        ):
            failures.append(
                "compiled prompt is missing the cross-medium conversion clause"
            )
        if (
            content_entry.get("provenance") == "fallback-medium-original"
            and "source-medium-derived adaptation" not in prompt
        ):
            failures.append(
                "compiled prompt does not label fallback-medium-original provenance"
            )
        selected_content_source = "manga-curated" if medium == "manga" else "tv-curated"
        selected_result = retrieval_result(evidence, "Selected-medium result")
        fallback_result = retrieval_result(evidence, "Cross-medium fallback result")
        if content_entry.get("source_id") == selected_content_source:
            if selected_result != "HIT":
                failures.append(
                    "selected-medium content requires a recorded HIT before selection"
                )
        else:
            if selected_result not in {"MISS", "INSUFFICIENT"}:
                failures.append(
                    "cross-medium content requires selected-medium MISS or INSUFFICIENT"
                )
            if fallback_result != "HIT":
                failures.append("cross-medium content requires a recorded fallback HIT")

    if intent in {"edit", "microfix"} and (not resolved or resolved[0][0] != "target"):
        failures.append("edit tasks require a target reference first")
    if intent == "microfix" and any(role == "continuity" for role, _ in resolved):
        failures.append(
            "microfix tasks must use the target, not a continuity duplicate"
        )
    if brief.get("deliverable") == "comparison":
        failures.append("comparison must use separate manga and TV tasks")

    if args.stage == "final":
        qa = load_json(task_dir / "qa.json", failures)
        checks = qa.get("checks", [])
        if not checks:
            failures.append("qa.json contains no checks")
        for check in checks:
            status = check.get("status")
            if status not in {"pass", "n/a"}:
                failures.append(
                    f"QA is not complete: {check.get('check', '[unnamed check]')}"
                )
            if status == "pass" and not check.get("note"):
                failures.append(
                    f"QA pass has no note: {check.get('check', '[unnamed check]')}"
                )
        result = load_json(task_dir / "result.json", failures)
        if brief_schema >= BRIEF_SCHEMA_VERSION:
            if result.get("schema_version") != RESULT_SCHEMA_VERSION:
                failures.append(
                    f"result.schema_version must be {RESULT_SCHEMA_VERSION}"
                )
            revisions = result.get("revisions") or []
            if not isinstance(revisions, list) or any(
                not isinstance(revision, dict) for revision in revisions
            ):
                failures.append("result.revisions must be a list of objects")
            accepted_attempt = result.get("accepted_attempt")
            attempt_path = (
                task_dir / "attempts" / f"{accepted_attempt:03d}" / "attempt.json"
                if isinstance(accepted_attempt, int)
                else None
            )
            if attempt_path is None or not attempt_path.is_file():
                failures.append("result.accepted_attempt must resolve to attempt.json")
            else:
                attempt = load_json(attempt_path, failures)
                if attempt.get("status") != "accepted":
                    failures.append("result.accepted_attempt is not accepted")
        if result.get("status") != "accepted":
            failures.append("result.status must be accepted")
        output = output_path(result)
        if output is None or not output.is_file():
            failures.append(f"accepted output is missing: {output or '[not recorded]'}")
        local_edit = brief.get("local_edit") or {}
        if (
            output is not None
            and output.is_file()
            and local_edit.get("mode") == "crop-composite"
        ):
            source_target = resolve_recorded_path(local_edit.get("target", ""))
            edit_box = tuple(local_edit.get("edit_box") or ())
            if not source_target.is_file():
                failures.append(f"local-edit source target is missing: {source_target}")
            elif len(edit_box) != 4 or not all(
                isinstance(value, int) for value in edit_box
            ):
                failures.append("local-edit edit_box must contain four integers")
            elif not outside_edit_box_equal(source_target, output, edit_box):
                failures.append("local-edit output changed pixels outside edit_box")
            report_path = output.with_suffix(".local-edit.json")
            if not report_path.is_file():
                failures.append(f"local-edit report is missing: {report_path}")
        if result.get("reference_audit_warning"):
            failures.append("accepted result still contains a reference audit warning")

    result = {
        "ok": not failures,
        "stage": args.stage,
        "task": str(task_dir),
        "reference_count": len(references),
        "failures": failures,
        "warnings": warnings,
        "latency": latency_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
