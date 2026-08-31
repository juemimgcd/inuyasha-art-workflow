#!/usr/bin/env python3
"""Build and optionally serve the read-only local reference gallery."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps, UnidentifiedImageError

from build_reference_index import freshness
from task_workflow import feedback_rank, reference_performance
from workflow_common import (
    atomic_write_json,
    atomic_write_text,
    library_signature,
    load_config,
    open_database,
    resolve_recorded_path,
    workflow_paths,
    workflow_root,
)

THUMBNAIL_MAX_EDGE = 480
VISIBLE_DOMAINS = ("identity", "character-style", "scene", "continuity")
JSON_FIELDS = {
    "subjects": list,
    "forms": list,
    "subject_forms": dict,
    "shot_types": list,
    "tags": list,
    "eligible_roles": list,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument(
        "--query-results",
        type=Path,
        help="Optional JSON output from an existing retrieval CLI.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the generated gallery with the standard-library HTTP server.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def ensure_safe_output(gallery: Path, config: dict) -> None:
    resolved = gallery.resolve()
    for source in config.get("sources", []):
        source_root = Path(source["path"]).resolve()
        if is_within(resolved, source_root):
            raise ValueError(f"gallery output cannot be inside source library: {source_root}")


def parse_json_field(row: dict, field: str, expected_type: type):
    value = json.loads(row[field])
    if not isinstance(value, expected_type):
        raise ValueError(f"{field} must decode to {expected_type.__name__}")
    return value


def trait_values(tags: list[str], prefix: str) -> list[str]:
    marker = f"{prefix}:"
    return sorted(
        {tag[len(marker) :] for tag in tags if isinstance(tag, str) and tag.startswith(marker)},
        key=str.casefold,
    )


def retrieval_query(item: dict) -> str | None:
    source_id = item["source_id"]
    if source_id == "manga-curated":
        args = ["--medium", "manga"]
    elif source_id == "tv-curated":
        args = ["--medium", "tv"]
    elif source_id == "selected-output":
        args = ["--source", "selected-output"]
    else:
        return None

    domain = item["reference_domain"]
    args += ["--reference-domain", domain]
    pairs = [
        (subject, form)
        for subject, forms in item["subject_forms"].items()
        for form in forms
    ]
    if domain in {"character-style", "scene"}:
        args += ["--role", "rendering"]
    if domain == "character-style" and pairs:
        args += ["--prefer-subject-form", f"{pairs[0][0]}={pairs[0][1]}"]
    elif item["subjects"]:
        args += ["--subject", item["subjects"][0]]
    if item["shot_types"]:
        args += ["--shot", item["shot_types"][0]]
    if item["view_angles"] and domain != "scene":
        args += ["--view-angle", item["view_angles"][0]]
    if item["scene_ids"]:
        args += ["--exact-term", f"scene-id:{item['scene_ids'][0]}"]
    command = [
        "scripts/run-python",
        "scripts/browse_curated_styles.py",
        *args,
        "--json",
    ]
    return " ".join(shlex.quote(value) for value in command)


def load_query_results(path: Path | None) -> tuple[dict | None, dict[str, dict]]:
    if path is None:
        return None, {}
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("query results must be a JSON object")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("query results must contain a candidates list")
    results = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("item_id"), str):
            raise ValueError("every query candidate must contain an item_id")
        reasons = candidate.get("match_reasons", [])
        if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
            raise ValueError("query candidate match_reasons must be a string list")
        results[candidate["item_id"]] = {
            "score": candidate.get("score"),
            "match_reasons": reasons,
            "position": candidate.get("position"),
        }
    context_keys = (
        "source_id",
        "reference_domain",
        "medium",
        "query",
        "intent_text",
        "exact_terms",
        "subjects",
        "forms",
        "preferred_subject_forms",
        "shots",
        "view_angle",
        "role",
    )
    return {key: payload.get(key) for key in context_keys}, results


def make_thumbnail(source: Path, destination: Path) -> None:
    if destination.is_file():
        return
    with Image.open(source) as image:
        rendered = ImageOps.exif_transpose(image)
        rendered.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE), Image.Resampling.LANCZOS)
        if rendered.mode != "RGB":
            background = Image.new("RGB", rendered.size, "white")
            if "A" in rendered.getbands():
                background.paste(rendered, mask=rendered.getchannel("A"))
            else:
                background.paste(rendered.convert("RGB"))
            rendered = background
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        rendered.save(temporary, format="JPEG", quality=84, optimize=True)
        temporary.replace(destination)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_json(
    attempt_dir: Path,
    task_dir: Path,
    name: str,
    errors: list[dict],
) -> tuple[dict | list | None, str]:
    snapshot = attempt_dir / name
    fallback = task_dir / name
    selected = snapshot if snapshot.is_file() else fallback if fallback.is_file() else None
    if selected is None:
        return None, "incomplete-provenance"
    try:
        value = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append({"path": str(selected), "error": str(exc)})
        return None, "incomplete-provenance"
    return value, "snapshot" if selected == snapshot else "legacy-fallback"


def artifact_text(
    attempt_dir: Path,
    task_dir: Path,
    name: str,
    errors: list[dict],
) -> tuple[str | None, str]:
    snapshot = attempt_dir / name
    fallback = task_dir / name
    selected = snapshot if snapshot.is_file() else fallback if fallback.is_file() else None
    if selected is None:
        return None, "incomplete-provenance"
    try:
        value = selected.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append({"path": str(selected), "error": str(exc)})
        return None, "incomplete-provenance"
    return value, "snapshot" if selected == snapshot else "legacy-fallback"


def relative_gallery_url(path: Path, root: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return "../" + quote(relative.as_posix(), safe="/")


def attempt_number(path: Path) -> int:
    try:
        return int(path.parent.name)
    except ValueError:
        return -1


def decision_generation_attempt(attempt: dict) -> int | None:
    for field in (
        "decision_from_attempt",
        "accepted_from_attempt",
        "rejected_from_attempt",
    ):
        value = attempt.get(field)
        if type(value) is int and value > 0:
            return value
    return None


def candidate_generation_attempt(
    tasks_root: Path,
    task_id: str,
    source_attempt: int,
) -> int:
    """Map a decision marker back to the generation attempt it decided."""
    path = (
        tasks_root
        / task_id
        / "attempts"
        / f"{source_attempt:03d}"
        / "attempt.json"
    )
    try:
        attempt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return source_attempt
    if not isinstance(attempt, dict):
        return source_attempt
    return decision_generation_attempt(attempt) or source_attempt


def normalized_check_rows(value) -> list[dict]:
    return value if isinstance(value, list) else []


def read_attempts(config: dict, root: Path, gallery: Path) -> dict:
    tasks_root = workflow_paths(root)["tasks"]
    errors: list[dict] = []
    task_records = {}
    child_tasks: dict[str, list[str]] = {}
    exact_repairs: dict[tuple[str, int], list[str]] = {}

    for task_dir in sorted(tasks_root.iterdir(), key=lambda path: path.name.casefold()):
        if not task_dir.is_dir():
            continue
        try:
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            brief = {}
        archived = (task_dir / "archived.json").is_file()
        task_records[task_dir.name] = {"brief": brief, "archived": archived}
        parent = brief.get("parent_task_id")
        if isinstance(parent, str) and parent:
            child_tasks.setdefault(parent, []).append(task_dir.name)
        candidate_source = brief.get("candidate_source")
        if isinstance(candidate_source, dict):
            source_task = candidate_source.get("task_id") or candidate_source.get("source_task_id")
            source_attempt = candidate_source.get("attempt") or candidate_source.get("attempt_number")
            if (
                isinstance(source_task, str)
                and type(source_attempt) is int
                and source_attempt > 0
            ):
                source_attempt = candidate_generation_attempt(
                    tasks_root, source_task, source_attempt
                )
                exact_repairs.setdefault((source_task, source_attempt), []).append(task_dir.name)

    cases = []
    for task_id, task_record in sorted(task_records.items()):
        task_dir = tasks_root / task_id
        attempt_paths = sorted(
            task_dir.glob("attempts/*/attempt.json"), key=attempt_number
        )
        attempts = []
        for path in attempt_paths:
            try:
                attempt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append({"path": str(path), "error": str(exc)})
                continue
            attempt["_path"] = path
            recorded_number = attempt.get("attempt")
            attempt["_number"] = (
                recorded_number if isinstance(recorded_number, int) else attempt_number(path)
            )
            attempts.append(attempt)

        decisions: dict[int, list[dict]] = {}
        generations = []
        for attempt in attempts:
            decision_from = decision_generation_attempt(attempt)
            if attempt.get("counts_as_generation") is False or isinstance(decision_from, int):
                if isinstance(decision_from, int):
                    decisions.setdefault(decision_from, []).append(attempt)
                else:
                    errors.append({
                        "path": str(attempt["_path"]),
                        "error": "decision attempt has no generation attempt link",
                    })
                continue
            generations.append(attempt)

        for attempt in generations:
            number = attempt["_number"]
            attempt_dir = attempt["_path"].parent
            brief, brief_source = artifact_json(attempt_dir, task_dir, "brief.json", errors)
            manifest, manifest_source = artifact_json(
                attempt_dir, task_dir, "reference-manifest.json", errors
            )
            qa, qa_source = artifact_json(attempt_dir, task_dir, "qa.json", errors)
            compile_report, compile_source = artifact_json(
                attempt_dir, task_dir, "prompt-compile.json", errors
            )
            compiled_prompt, compiled_source = artifact_text(
                attempt_dir, task_dir, "prompt.md", errors
            )
            submitted_prompt, submitted_source = artifact_text(
                attempt_dir, task_dir, "submitted-prompt.md", errors
            )
            if submitted_prompt is None and attempt.get("submitted_prompt_source") == "compiled-verbatim":
                expected = attempt.get("submitted_prompt_sha256")
                if compiled_prompt is not None and expected == hashlib.sha256(
                    compiled_prompt.encode("utf-8")
                ).hexdigest():
                    submitted_prompt = compiled_prompt
                    submitted_source = compiled_source

            brief = brief if isinstance(brief, dict) else {}
            manifest = manifest if isinstance(manifest, dict) else {}
            qa = qa if isinstance(qa, dict) else {}
            linked = sorted(decisions.get(number, []), key=lambda row: row["_number"])
            effective_status = attempt.get("status", "unknown")
            for decision in linked:
                if decision.get("status") in {"accepted", "rejected"}:
                    effective_status = decision["status"]

            output_path = None
            output_error = None
            output_url = None
            thumbnail_url = None
            recorded_output = attempt.get("output")
            if isinstance(recorded_output, str) and recorded_output:
                output_path = resolve_recorded_path(recorded_output, config)
                output_url = relative_gallery_url(output_path, root)
                expected_hash = attempt.get("output_sha256")
                if not output_path.is_file():
                    output_error = f"output image is missing: {output_path}"
                else:
                    try:
                        actual_hash = sha256_file(output_path)
                        if isinstance(expected_hash, str) and actual_hash != expected_hash:
                            output_error = f"output hash mismatch: {output_path}"
                        else:
                            thumbnail = gallery / "attempt-thumbnails" / f"{actual_hash}.jpg"
                            make_thumbnail(output_path, thumbnail)
                            thumbnail_url = f"attempt-thumbnails/{thumbnail.name}"
                            if output_url is None:
                                cached_output = gallery / "attempt-outputs" / (
                                    f"{actual_hash}{output_path.suffix.lower()}"
                                )
                                if not cached_output.is_file() or sha256_file(cached_output) != actual_hash:
                                    cached_output.parent.mkdir(parents=True, exist_ok=True)
                                    temporary = cached_output.with_name(f".{cached_output.name}.tmp")
                                    shutil.copyfile(output_path, temporary)
                                    temporary.replace(cached_output)
                                output_url = f"attempt-outputs/{cached_output.name}"
                    except (OSError, UnidentifiedImageError) as exc:
                        output_error = str(exc)

            actual_inputs = attempt.get("actual_input_images")
            actual_inputs = actual_inputs if isinstance(actual_inputs, list) else []
            input_rows = []
            for item in actual_inputs:
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                path_value = row.get("path")
                if isinstance(path_value, str) and path_value:
                    resolved = resolve_recorded_path(path_value, config)
                    row["source_path"] = str(resolved)
                    row["image_url"] = relative_gallery_url(resolved, root)
                input_rows.append(row)

            reference_rows = manifest.get("references")
            reference_rows = reference_rows if isinstance(reference_rows, list) else []
            reference_ids = attempt.get("reference_item_ids")
            if not isinstance(reference_ids, list):
                reference_ids = [
                    row.get("item_id") for row in reference_rows
                    if isinstance(row, dict) and isinstance(row.get("item_id"), str)
                ]
            identity_forms = brief.get("identity_forms")
            identity_forms = identity_forms if isinstance(identity_forms, dict) else {}
            characters = brief.get("characters")
            characters = characters if isinstance(characters, list) else list(identity_forms)
            provenance = {
                "brief": brief_source,
                "manifest": manifest_source,
                "qa": qa_source,
                "compiled_prompt": compiled_source,
                "submitted_prompt": submitted_source,
                "prompt_compile": compile_source,
            }
            relationship_children = sorted(set(child_tasks.get(task_id, [])))
            repairs = sorted(set(exact_repairs.get((task_id, number), [])))
            decision_chain = [
                {
                    "attempt": row["_number"],
                    "status": row.get("status"),
                    "recorded_at": row.get("recorded_at"),
                    "user_feedback": row.get("user_feedback"),
                    "failures": normalized_check_rows(row.get("failures")),
                }
                for row in linked
            ]
            all_failures = [
                *normalized_check_rows(attempt.get("failures")),
                *(failure for row in linked for failure in normalized_check_rows(row.get("failures"))),
            ]
            feedback = [
                value for value in [attempt.get("user_feedback"), *(
                    row.get("user_feedback") for row in linked
                )] if isinstance(value, str) and value
            ]
            cases.append({
                "case_id": f"{task_id}:{number:03d}",
                "task_id": task_id,
                "generation_attempt": number,
                "decision_attempt": linked[-1]["_number"] if linked else None,
                "decision_chain": decision_chain,
                "generated_status": attempt.get("status", "unknown"),
                "effective_status": effective_status,
                "archived": task_record["archived"],
                "recorded_at": attempt.get("recorded_at"),
                "request": brief.get("request") or brief.get("change_request") or "",
                "intent": brief.get("intent") or "legacy",
                "medium": brief.get("medium") or "unknown",
                "characters": characters,
                "identity_forms": identity_forms,
                "forms": sorted(set(identity_forms.values())),
                "shot": brief.get("shot"),
                "view_angle": brief.get("view_angle"),
                "change_category": brief.get("change_category"),
                "change_scope": brief.get("change_scope"),
                "parent_task_id": brief.get("parent_task_id"),
                "candidate_source": brief.get("candidate_source"),
                "child_tasks": relationship_children,
                "later_bounded_repairs": repairs,
                "has_later_bounded_repair": bool(repairs),
                "output_path": str(output_path) if output_path else None,
                "output_url": output_url,
                "thumbnail": thumbnail_url,
                "output_error": output_error,
                "reference_item_ids": reference_ids,
                "reference_count": len(reference_ids),
                "reference_manifest": reference_rows,
                "actual_input_images": input_rows,
                "compiled_prompt": compiled_prompt,
                "submitted_prompt": submitted_prompt,
                "compiled_prompt_sha256": attempt.get("compiled_prompt_sha256"),
                "submitted_prompt_sha256": attempt.get("submitted_prompt_sha256"),
                "submitted_prompt_differs_from_compiled": attempt.get("submitted_prompt_differs_from_compiled"),
                "prompt_length": len(compiled_prompt) if compiled_prompt is not None else None,
                "prompt_compile": compile_report if isinstance(compile_report, dict) else None,
                "preview_checks": normalized_check_rows(attempt.get("preview_checks")),
                "medium_component_checks": normalized_check_rows(attempt.get("medium_component_checks")),
                "qa": qa,
                "failures": normalized_check_rows(attempt.get("failures")),
                "failure_categories": sorted({
                    row.get("category", "unknown") for row in all_failures
                    if isinstance(row, dict)
                }),
                "user_feedback": feedback,
                "generator": attempt.get("generator"),
                "duration_seconds": attempt.get("duration_seconds"),
                "generation_seconds": attempt.get("generation_seconds"),
                "pre_generation_seconds": attempt.get("pre_generation_seconds"),
                "post_generation_seconds": attempt.get("post_generation_seconds"),
                "workflow_overhead_seconds": attempt.get("workflow_overhead_seconds"),
                "network_failure": attempt.get("network_failure"),
                "transport_retry_exhausted": attempt.get("transport_retry_exhausted"),
                "submission_tracked": bool(attempt.get("generation_submission_sha256")),
                "generation_transport": attempt.get("generation_transport"),
                "provenance": provenance,
                "legacy_fallback": "legacy-fallback" in provenance.values(),
                "incomplete_provenance": "incomplete-provenance" in provenance.values(),
            })

    cases.sort(key=lambda row: (row["recorded_at"] or "", row["case_id"]), reverse=True)
    return {
        "schema_version": 1,
        "tasks_path": str(tasks_root),
        "count": len(cases),
        "generation_count": sum(case["generated_status"] != "error" for case in cases),
        "error_count": sum(case["generated_status"] == "error" for case in cases),
        "archived_count": sum(case["archived"] for case in cases),
        "errors": errors,
        "cases": cases,
    }


def read_summary(root: Path) -> dict:
    command = [
        sys.executable,
        str(Path(__file__).with_name("reference_feedback_report.py")),
        "--workflow-root",
        str(root),
        "--json",
    ]
    process = subprocess.run(command, check=False, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "reference feedback report failed")
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise ValueError("reference feedback report must be a JSON object")
    return value


def read_references(config: dict, root: Path, gallery: Path, query_path: Path | None) -> dict:
    paths = workflow_paths(root)
    database = paths["database"]
    if not database.is_file():
        raise FileNotFoundError(f"catalog missing: {database}")
    fresh, reason = freshness(
        database, config, library_signature(config), paths["annotations"]
    )
    if not fresh:
        raise RuntimeError(
            f"Catalog is stale: {reason}; run build_reference_index.py"
        )
    query_context, query_items = load_query_results(query_path)
    performance = reference_performance(paths["tasks"])
    connection = open_database(database, read_only=True)
    placeholders = ",".join("?" for _ in VISIBLE_DOMAINS)
    rows = connection.execute(
        f"""
        SELECT items.item_id, items.source_id, items.reference_domain,
               items.path, items.relative_path, items.content_hash,
               items.content_label, items.subjects, items.forms,
               items.subject_forms, items.shot_types, items.tags,
               items.eligible_roles, items.width, items.height,
               sources.label AS source_label, sources.medium
        FROM items
        JOIN sources USING (source_id)
        WHERE items.kind = 'image'
          AND items.reference_domain IN ({placeholders})
        ORDER BY items.relative_path COLLATE NOCASE, items.item_id
        """,
        VISIBLE_DOMAINS,
    ).fetchall()
    connection.close()

    thumbnails = gallery / "thumbnails"
    items = []
    errors = []
    for raw_row in rows:
        row = dict(raw_row)
        try:
            for field, expected_type in JSON_FIELDS.items():
                row[field] = parse_json_field(row, field, expected_type)
            if not row["content_hash"]:
                raise ValueError("content_hash is missing")
            row["view_angles"] = trait_values(row["tags"], "view-angle")
            row["scene_ids"] = trait_values(row["tags"], "scene-id")
            row["scene_economy"] = trait_values(row["tags"], "scene-economy")
            row["black_mass"] = trait_values(row["tags"], "black-mass")
            row["tone_density"] = trait_values(row["tags"], "tone-density")
            row["detail_falloff"] = trait_values(row["tags"], "detail-falloff")
            row["certified_style_anchor"] = "style-anchor:certified" in row["tags"]
            stats = performance.get(
                row["item_id"],
                {"accepted": 0, "rejected": 0, "total": 0, "smoothed_acceptance": 0.5},
            )
            row["reference_outcomes"] = {
                **stats,
                "feedback_rank": round(feedback_rank(stats), 4),
            }
            row["retrieval"] = query_items.get(row["item_id"])
            source = resolve_recorded_path(row["path"], config)
            row["source_path"] = str(source)
            thumbnail = thumbnails / f"{row['content_hash']}.jpg"
            try:
                if not source.is_file():
                    raise FileNotFoundError(f"source image is missing: {source}")
                make_thumbnail(source, thumbnail)
                row["thumbnail"] = f"thumbnails/{thumbnail.name}"
                row["image_error"] = None
            except (FileNotFoundError, OSError, UnidentifiedImageError) as exc:
                row["thumbnail"] = None
                row["image_error"] = str(exc)
                errors.append({"item_id": row["item_id"], "error": str(exc)})
            row["browse_query"] = retrieval_query(row)
            row["invalid"] = False
            row.pop("path", None)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            row = {
                "item_id": str(row.get("item_id", "unknown")),
                "relative_path": str(row.get("relative_path", "")),
                "invalid": True,
                "data_error": str(exc),
                "thumbnail": None,
            }
            errors.append({"item_id": row["item_id"], "error": str(exc)})
        items.append(row)
    return {
        "schema_version": 1,
        "catalog_path": str(database),
        "count": len(items),
        "query_context": query_context,
        "query_result_count": len(query_items),
        "errors": errors,
        "items": items,
    }


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Inuyasha Workflow Gallery</title>
  <style>
    :root { color-scheme: light; --ink:#191714; --paper:#f7f3e9; --panel:#fffdf7; --line:#c9c0ae; --muted:#6d665a; --accent:#8b201e; --focus:#2458a6; }
    * { box-sizing:border-box; }
    [hidden] { display:none !important; }
    body { margin:0; color:var(--ink); background:var(--paper); font:15px/1.45 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    button,input,select { font:inherit; }
    button,select,input { border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--ink); }
    button { padding:.58rem .78rem; cursor:pointer; }
    button:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); }
    button:disabled { cursor:not-allowed; opacity:.48; }
    :focus-visible { outline:3px solid color-mix(in srgb,var(--focus) 55%,transparent); outline-offset:2px; }
    header { padding:1.25rem clamp(1rem,3vw,2.5rem); border-bottom:1px solid var(--line); background:var(--panel); }
    h1 { margin:0; font:700 clamp(1.55rem,3vw,2.25rem)/1.1 ui-serif,Georgia,serif; }
    header p { max-width:68rem; margin:.55rem 0 0; color:var(--muted); }
    .tabs { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:1rem; }
    .tabs button[aria-selected="true"] { border-color:var(--accent); color:#fff; background:var(--accent); }
    main { padding:1rem clamp(1rem,3vw,2.5rem) 3rem; }
    .filters { display:grid; grid-template-columns:minmax(14rem,2fr) repeat(3,minmax(9rem,1fr)); gap:.75rem; padding:1rem; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
    .field { display:grid; align-content:start; gap:.3rem; min-width:0; }
    .field label { color:var(--muted); font-size:.82rem; font-weight:650; }
    .field input,.field select { width:100%; min-height:2.45rem; padding:.5rem .6rem; }
    .filter-actions { display:flex; align-items:end; gap:.5rem; }
    .check { display:flex; align-items:center; gap:.48rem; padding:.45rem 0; }
    .check input { inline-size:1.05rem; block-size:1.05rem; }
    .meta { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:.7rem; min-height:3.4rem; color:var(--muted); }
    .state { padding:2rem; border:1px dashed var(--line); border-radius:10px; background:var(--panel); text-align:center; }
    .state[hidden] { display:none; }
    .error { color:#8a1715; }
    .grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; }
    .card { min-width:0; overflow:hidden; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
    .thumb { display:grid; place-items:center; inline-size:100%; aspect-ratio:4/3; overflow:hidden; border-bottom:1px solid var(--line); background:#e9e2d4; }
    .thumb img { inline-size:100%; block-size:100%; object-fit:contain; }
    .placeholder { max-width:22rem; padding:1rem; color:var(--muted); text-align:center; }
    .card-body { display:grid; gap:.7rem; padding:.9rem; }
    .eyebrow { color:var(--accent); font-size:.76rem; font-weight:750; letter-spacing:.04em; text-transform:uppercase; }
    .item-id { margin:0; overflow-wrap:anywhere; font:650 .95rem/1.35 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .path { margin:0; color:var(--muted); overflow-wrap:anywhere; }
    .chips { display:flex; flex-wrap:wrap; gap:.35rem; }
    .chip { max-width:100%; padding:.18rem .42rem; border:1px solid var(--line); border-radius:999px; overflow-wrap:anywhere; background:#fff; font-size:.75rem; }
    .outcome { display:flex; gap:.8rem; color:var(--muted); font-size:.82rem; }
    .card-facts { grid-template-columns:minmax(6.5rem,8rem) 1fr; gap:.3rem .55rem; font-size:.78rem; }
    .card-facts dd { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
    .card button { justify-self:start; }
    dialog { width:min(54rem,calc(100% - 2rem)); max-height:calc(100dvh - 2rem); padding:0; border:1px solid var(--line); border-radius:12px; color:var(--ink); background:var(--panel); box-shadow:0 18px 50px #0003; }
    dialog::backdrop { background:#17130f99; }
    .dialog-head { position:sticky; top:0; display:flex; justify-content:space-between; gap:1rem; padding:1rem; border-bottom:1px solid var(--line); background:var(--panel); z-index:1; }
    .dialog-head h2 { margin:0; overflow-wrap:anywhere; font-size:1.05rem; }
    .dialog-body { display:grid; gap:1rem; padding:1rem; }
    .detail-image { max-width:100%; max-height:60dvh; margin:auto; object-fit:contain; background:#eee8da; }
    dl { display:grid; grid-template-columns:minmax(9rem,13rem) 1fr; gap:.55rem 1rem; margin:0; }
    dt { color:var(--muted); font-weight:650; }
    dd { margin:0; min-width:0; overflow-wrap:anywhere; }
    pre { overflow:auto; margin:0; padding:.8rem; border:1px solid var(--line); border-radius:6px; background:#f1ece1; white-space:pre-wrap; word-break:break-word; }
    .copy-actions { display:flex; flex-wrap:wrap; gap:.5rem; }
    .summary-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; }
    .summary-card { padding:1rem; border:1px solid var(--line); border-radius:10px; background:var(--panel); }
    .summary-card h2 { margin:0 0 .65rem; font-size:1rem; }
    .summary-card strong { display:block; font:700 1.75rem/1 ui-serif,Georgia,serif; }
    .summary-card p { margin:.45rem 0 0; color:var(--muted); }
    .detail-section { display:grid; gap:.5rem; }
    .detail-section h3 { margin:.25rem 0 0; font-size:1rem; }
    .input-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.75rem; }
    .input-item { min-width:0; padding:.7rem; border:1px solid var(--line); border-radius:8px; }
    .input-item img { width:100%; max-height:18rem; object-fit:contain; background:#eee8da; }
    @media (max-width:1050px) { .filters { grid-template-columns:repeat(3,minmax(0,1fr)); } .field.search { grid-column:1/-1; } .grid,.summary-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width:700px) { .filters { grid-template-columns:1fr; } .field.search { grid-column:auto; } .grid,.summary-grid,.input-list { grid-template-columns:1fr; } dl { grid-template-columns:1fr; gap:.15rem; } dd { margin-bottom:.55rem; } }
  </style>
</head>
<body>
  <header>
    <h1>Inuyasha Workflow Gallery</h1>
    <p>参考目录、生成 casebook 与反馈指标的只读派生视图。浏览不会改变参考图、manifest、attempt、result 或偏好数据。</p>
    <nav class="tabs" aria-label="Gallery views">
      <button type="button" data-tab="references" aria-selected="true">References</button>
      <button type="button" data-tab="attempts" aria-selected="false">Attempts</button>
      <button type="button" data-tab="summary" aria-selected="false">Summary</button>
    </nav>
  </header>
  <main>
    <section id="referencesView">
    <section class="filters" aria-label="参考图筛选">
      <div class="field search"><label for="search">搜索路径、ID、标签或内容</label><input id="search" type="search" disabled autocomplete="off"></div>
      <div class="field"><label for="medium">媒介</label><select id="medium" disabled><option value="">全部</option><option value="manga">Manga</option><option value="tv">TV</option></select></div>
      <div class="field"><label for="domain">Authority domain</label><select id="domain" disabled><option value="">全部</option><option>identity</option><option>character-style</option><option>scene</option><option>continuity</option></select></div>
      <div class="field"><label for="subject">角色 / subject</label><select id="subject" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="form">精确 form</label><select id="form" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="shot">Shot</label><select id="shot" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="view">View angle</label><select id="view" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="sceneId">Canonical scene ID</label><select id="sceneId" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="sceneEconomy">Scene economy</label><select id="sceneEconomy" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="blackMass">Black mass</label><select id="blackMass" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="tone">Tone density</label><select id="tone" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="falloff">Detail falloff</label><select id="falloff" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="role">Eligible role</label><select id="role" disabled><option value="">全部</option></select></div>
      <div class="field"><label for="outcome">历史 reference use</label><select id="outcome" disabled><option value="">全部</option><option value="accepted">Accepted use</option><option value="rejected">Explicitly blamed rejection</option><option value="unused">No decided use</option></select></div>
      <div class="field">
        <label>布尔筛选</label>
        <label class="check"><input id="certified" type="checkbox" disabled> Certified style anchor</label>
        <label class="check"><input id="negativeSpace" type="checkbox" disabled> Authored negative space</label>
        <label class="check" id="queryOnlyRow" hidden><input id="queryOnly" type="checkbox" disabled checked> 只看传入检索结果</label>
      </div>
      <div class="filter-actions"><button id="clear" type="button" disabled>清除筛选</button></div>
    </section>
    <div class="meta"><span id="status" role="status" aria-live="polite">正在读取 references.json…</span><span id="queryContext"></span></div>
    <section id="loading" class="state">正在加载参考图索引…</section>
    <section id="empty" class="state" hidden>没有符合当前筛选条件的参考图。</section>
    <section id="error" class="state error" hidden></section>
    <section id="grid" class="grid" aria-label="参考图结果"></section>
    </section>

    <section id="attemptsView" hidden>
      <section class="filters" aria-label="生成案例筛选">
        <div class="field search"><label for="attemptSearch">搜索 task、请求、反馈、失败或 reference ID</label><input id="attemptSearch" type="search" disabled autocomplete="off"></div>
        <div class="field"><label for="caseType">案例视图</label><select id="caseType" disabled><option value="generation">Generations</option><option value="error">Errors</option></select></div>
        <div class="field"><label for="effectiveStatus">Effective status</label><select id="effectiveStatus" disabled><option value="">全部</option><option>accepted</option><option>candidate</option><option>rejected</option></select></div>
        <div class="field"><label for="attemptCharacter">角色</label><select id="attemptCharacter" disabled><option value="">全部</option></select></div>
        <div class="field"><label for="attemptForm">精确 form</label><select id="attemptForm" disabled><option value="">全部</option></select></div>
        <div class="field"><label for="attemptIntent">Intent</label><select id="attemptIntent" disabled><option value="">全部</option><option>new</option><option>edit</option><option>microfix</option><option>legacy</option></select></div>
        <div class="field"><label for="attemptShot">Shot</label><select id="attemptShot" disabled><option value="">全部</option></select></div>
        <div class="field"><label for="attemptView">View angle</label><select id="attemptView" disabled><option value="">全部</option></select></div>
        <div class="field"><label for="attemptFailure">Failure category</label><select id="attemptFailure" disabled><option value="">全部</option></select></div>
        <div class="field"><label for="attemptGenerator">Generator</label><select id="attemptGenerator" disabled><option value="">全部</option></select></div>
        <div class="field"><label for="promptDiff">Compiled / submitted</label><select id="promptDiff" disabled><option value="">全部</option><option value="different">Different</option><option value="same">Same</option><option value="unknown">Unknown</option></select></div>
        <div class="field"><label for="submissionState">Submission tracking</label><select id="submissionState" disabled><option value="">全部</option><option value="tracked">Tracked</option><option value="untracked">Untracked</option></select></div>
        <div class="field"><label for="attemptReference">Reference item ID</label><select id="attemptReference" disabled><option value="">全部</option></select></div>
        <div class="field"><label for="attemptProvenance">Provenance</label><select id="attemptProvenance" disabled><option value="">全部</option><option value="complete">Snapshot complete</option><option value="legacy">Legacy fallback</option><option value="incomplete">Incomplete</option></select></div>
        <div class="field"><label>布尔筛选</label><label class="check"><input id="retryExhausted" type="checkbox" disabled> Transport retry exhausted</label><label class="check"><input id="boundedRepair" type="checkbox" disabled> Later bounded repair</label><label class="check"><input id="includeArchived" type="checkbox" disabled> Include archived</label></div>
        <div class="filter-actions"><button id="clearAttempts" type="button" disabled>清除筛选</button></div>
      </section>
      <div class="meta"><span id="attemptStatus" role="status" aria-live="polite">正在读取 attempts.json…</span></div>
      <section id="attemptLoading" class="state">正在加载生成案例…</section>
      <section id="attemptEmpty" class="state" hidden>没有符合当前筛选条件的生成案例。</section>
      <section id="attemptError" class="state error" hidden></section>
      <section id="attemptGrid" class="grid" aria-label="生成案例结果"></section>
    </section>

    <section id="summaryView" hidden>
      <div class="meta"><span id="summaryStatus" role="status" aria-live="polite">正在读取 summary.json…</span></div>
      <section id="summaryLoading" class="state">正在加载反馈摘要…</section>
      <section id="summaryError" class="state error" hidden></section>
      <section id="summaryGrid" class="summary-grid"></section>
    </section>
  </main>
  <dialog id="detail"><div class="dialog-head"><h2 id="detailTitle"></h2><button id="closeDetail" type="button">关闭</button></div><div id="detailBody" class="dialog-body"></div></dialog>
  <dialog id="attemptDetail"><div class="dialog-head"><h2 id="attemptDetailTitle"></h2><button id="closeAttemptDetail" type="button">关闭</button></div><div id="attemptDetailBody" class="dialog-body"></div></dialog>
  <script>
    const ids = ["search","medium","domain","subject","form","shot","view","sceneId","sceneEconomy","blackMass","tone","falloff","role","outcome","certified","negativeSpace","queryOnly"];
    const controls = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
    const state = { items: [], byId: new Map(), queryContext: null, current: null };
    const attemptIds = ["attemptSearch","caseType","effectiveStatus","attemptCharacter","attemptForm","attemptIntent","attemptShot","attemptView","attemptFailure","attemptGenerator","promptDiff","submissionState","attemptReference","attemptProvenance","retryExhausted","boundedRepair","includeArchived"];
    const attemptControls = Object.fromEntries(attemptIds.map(id => [id, document.getElementById(id)]));
    const attemptState = { cases: [], byId: new Map(), current: null };
    let currentTab = new URLSearchParams(location.search).get("tab") || "references";
    const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
    const chips = values => `<div class="chips">${values.map(value => `<span class="chip">${esc(value)}</span>`).join("")}</div>`;
    const checkSummary = rows => (rows||[]).map(row=>`${row.category||row.component||"check"}=${row.result||"unknown"}`).join(" · ") || "—";
    const unique = (items, key) => [...new Set(items.flatMap(item => item.invalid ? [] : item[key] || []))].sort((a,b) => a.localeCompare(b));
    function populate(id, values) { controls[id].insertAdjacentHTML("beforeend", values.map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join("")); }
    function searchable(item) { return [item.item_id,item.relative_path,item.content_label,item.source_label,...(item.tags||[]),...(item.subjects||[]),...(item.forms||[])].join(" ").toLocaleLowerCase(); }
    function matches(item) {
      if (item.invalid) return !controls.search.value || searchable(item).includes(controls.search.value.toLocaleLowerCase());
      const subject = controls.subject.value, form = controls.form.value;
      if (controls.search.value && !searchable(item).includes(controls.search.value.toLocaleLowerCase())) return false;
      if (controls.medium.value && item.medium !== controls.medium.value) return false;
      if (controls.domain.value && item.reference_domain !== controls.domain.value) return false;
      if (subject && !(item.subjects||[]).includes(subject)) return false;
      if (form && (subject ? !(item.subject_forms?.[subject]||[]).includes(form) : !(item.forms||[]).includes(form))) return false;
      if (controls.shot.value && !(item.shot_types||[]).includes(controls.shot.value)) return false;
      if (controls.view.value && !(item.view_angles||[]).includes(controls.view.value)) return false;
      if (controls.sceneId.value && !(item.scene_ids||[]).includes(controls.sceneId.value)) return false;
      if (controls.sceneEconomy.value && !(item.scene_economy||[]).includes(controls.sceneEconomy.value)) return false;
      if (controls.blackMass.value && !(item.black_mass||[]).includes(controls.blackMass.value)) return false;
      if (controls.tone.value && !(item.tone_density||[]).includes(controls.tone.value)) return false;
      if (controls.falloff.value && !(item.detail_falloff||[]).includes(controls.falloff.value)) return false;
      if (controls.role.value && !(item.eligible_roles||[]).includes(controls.role.value)) return false;
      if (controls.certified.checked && !item.certified_style_anchor) return false;
      if (controls.negativeSpace.checked && !(item.scene_economy||[]).includes("authored-negative-space")) return false;
      if (state.queryContext && controls.queryOnly.checked && !item.retrieval) return false;
      const stats = item.reference_outcomes || {};
      if (controls.outcome.value === "accepted" && !stats.accepted) return false;
      if (controls.outcome.value === "rejected" && !stats.rejected) return false;
      if (controls.outcome.value === "unused" && stats.total) return false;
      return true;
    }
    function render() {
      const visible = state.items.filter(matches);
      document.getElementById("grid").innerHTML = visible.map(item => item.invalid ? `
        <article class="card"><div class="thumb"><div class="placeholder error">Invalid catalog row</div></div><div class="card-body"><p class="item-id">${esc(item.item_id)}</p><p class="path">${esc(item.data_error)}</p></div></article>` : `
        <article class="card">
          <div class="thumb">${item.thumbnail ? `<img src="${esc(item.thumbnail)}" alt="${esc(item.content_label || item.relative_path)}" loading="lazy">` : `<div class="placeholder error">${esc(item.image_error || "Missing image")}</div>`}</div>
          <div class="card-body"><div class="eyebrow">${esc(item.reference_domain)} · ${esc(item.medium)}</div><h2 class="item-id">${esc(item.item_id)}</h2><p class="path">${esc(item.content_label || item.relative_path)}</p>
          ${chips([...(item.subjects||[]),...(item.forms||[]),...(item.shot_types||[]),...(item.view_angles||[]).map(v=>`view:${v}`)].slice(0,10))}
          <div class="outcome"><span>accepted ${item.reference_outcomes.accepted}</span><span>rejected ${item.reference_outcomes.rejected}</span><span>smoothed ${item.reference_outcomes.smoothed_acceptance}</span></div>
          ${item.retrieval ? `<p class="path">检索命中：${esc((item.retrieval.match_reasons||[]).join("；") || "无记录理由")}</p>` : ""}
          <button type="button" data-detail="${esc(item.item_id)}">查看详情</button></div>
        </article>`).join("");
      document.getElementById("empty").hidden = visible.length !== 0;
      document.getElementById("status").textContent = `显示 ${visible.length} / ${state.items.length} 项`;
      const params = new URLSearchParams();
      for (const [id, control] of Object.entries(controls)) { const value = control.type === "checkbox" ? (control.checked ? "1" : "") : control.value; if (value) params.set(id,value); }
      if (currentTab === "references") history.replaceState(null,"",`${location.pathname}${params.size ? `?${params}` : ""}`);
    }
    function showDetail(item) {
      state.current = item;
      document.getElementById("detailTitle").textContent = item.item_id;
      const stats = item.reference_outcomes;
      document.getElementById("detailBody").innerHTML = `
        ${item.thumbnail ? `<img class="detail-image" src="${esc(item.thumbnail)}" alt="${esc(item.content_label || item.relative_path)}">` : `<div class="state error">${esc(item.image_error || "Missing image")}</div>`}
        <div class="copy-actions"><button type="button" data-copy="id">复制 item ID</button><button type="button" data-copy="path">复制 source path</button><button type="button" data-copy="query" ${item.browse_query ? "" : "disabled"}>复制 browse query</button></div>
        <dl><dt>Domain</dt><dd>${esc(item.reference_domain)}</dd><dt>Source</dt><dd>${esc(item.source_label)} (${esc(item.source_id)})</dd><dt>Relative path</dt><dd>${esc(item.relative_path)}</dd><dt>Source path</dt><dd>${esc(item.source_path)}</dd><dt>Content hash</dt><dd>${esc(item.content_hash)}</dd><dt>Dimensions</dt><dd>${esc(item.width)} × ${esc(item.height)}</dd><dt>Subject forms</dt><dd>${esc(JSON.stringify(item.subject_forms))}</dd><dt>Shot / view</dt><dd>${esc([...(item.shot_types||[]),...(item.view_angles||[]).map(v=>`view:${v}`)].join(", ") || "—")}</dd><dt>Eligible roles</dt><dd>${esc((item.eligible_roles||[]).join(", ") || "—")}</dd><dt>Certified</dt><dd>${item.certified_style_anchor ? "yes" : "no"}</dd><dt>Outcomes</dt><dd>accepted ${stats.accepted}; rejected ${stats.rejected}; smoothed ${stats.smoothed_acceptance}; rank ${stats.feedback_rank}</dd></dl>
        <div><strong>Controlled tags</strong>${chips(item.tags||[])}</div>
        ${item.retrieval ? `<div><strong>Retrieval match reasons</strong>${chips(item.retrieval.match_reasons||[])}</div>` : ""}
        ${item.browse_query ? `<div><strong>Equivalent query</strong><pre>${esc(item.browse_query)}</pre></div>` : ""}`;
      document.getElementById("detail").showModal();
    }
    async function copyCurrent(kind) {
      const item = state.current; const value = kind === "id" ? item.item_id : kind === "path" ? item.source_path : item.browse_query;
      if (!value) return;
      try { await navigator.clipboard.writeText(value); document.getElementById("status").textContent = "已复制。"; }
      catch { const area = document.createElement("textarea"); area.value=value; document.body.append(area); area.select(); document.execCommand("copy"); area.remove(); }
    }
    document.getElementById("grid").addEventListener("click", event => { const button=event.target.closest("[data-detail]"); if (button) showDetail(state.byId.get(button.dataset.detail)); });
    document.getElementById("detailBody").addEventListener("click", event => { const button=event.target.closest("[data-copy]"); if (button) copyCurrent(button.dataset.copy); });
    document.getElementById("closeDetail").addEventListener("click", () => document.getElementById("detail").close());
    document.getElementById("detail").addEventListener("click", event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
    for (const control of Object.values(controls)) control.addEventListener(control.type === "search" ? "input" : "change", render);
    document.getElementById("clear").addEventListener("click", () => { for (const control of Object.values(controls)) { if (control.type === "checkbox") control.checked=false; else control.value=""; } render(); controls.search.focus(); });

    function showTab(tab, updateUrl=true) {
      currentTab = ["references","attempts","summary"].includes(tab) ? tab : "references";
      for (const name of ["references","attempts","summary"]) {
        document.getElementById(`${name}View`).hidden = name !== currentTab;
        document.querySelector(`[data-tab="${name}"]`).setAttribute("aria-selected", name === currentTab ? "true" : "false");
      }
      if (updateUrl) {
        const params = new URLSearchParams();
        if (currentTab !== "references") params.set("tab", currentTab);
        history.replaceState(null,"",`${location.pathname}${params.size ? `?${params}` : ""}`);
      }
    }
    document.querySelector(".tabs").addEventListener("click", event => { const button=event.target.closest("[data-tab]"); if (button) showTab(button.dataset.tab); });
    showTab(currentTab, false);

    const attemptUnique = (key, flatten=false) => [...new Set(attemptState.cases.flatMap(item => {
      const value=item[key]; return flatten ? (Array.isArray(value) ? value : []) : value ? [value] : [];
    }))].sort((a,b)=>String(a).localeCompare(String(b)));
    function attemptSearchable(item) { return [item.case_id,item.task_id,item.request,item.generator,...(item.characters||[]),...(item.forms||[]),...(item.failure_categories||[]),...(item.reference_item_ids||[]),...(item.user_feedback||[]),JSON.stringify([item.qa,item.preview_checks,item.medium_component_checks,item.failures,item.decision_chain,item.candidate_source])].join(" ").toLocaleLowerCase(); }
    function attemptMatches(item) {
      const isError=item.generated_status === "error";
      if ((attemptControls.caseType.value === "error") !== isError) return false;
      if (!attemptControls.includeArchived.checked && item.archived) return false;
      if (attemptControls.attemptSearch.value && !attemptSearchable(item).includes(attemptControls.attemptSearch.value.toLocaleLowerCase())) return false;
      if (attemptControls.effectiveStatus.value && item.effective_status !== attemptControls.effectiveStatus.value) return false;
      if (attemptControls.attemptCharacter.value && !(item.characters||[]).includes(attemptControls.attemptCharacter.value)) return false;
      if (attemptControls.attemptForm.value && !(item.forms||[]).includes(attemptControls.attemptForm.value)) return false;
      if (attemptControls.attemptIntent.value && item.intent !== attemptControls.attemptIntent.value) return false;
      if (attemptControls.attemptShot.value && item.shot !== attemptControls.attemptShot.value) return false;
      if (attemptControls.attemptView.value && item.view_angle !== attemptControls.attemptView.value) return false;
      if (attemptControls.attemptFailure.value && !(item.failure_categories||[]).includes(attemptControls.attemptFailure.value)) return false;
      if (attemptControls.attemptGenerator.value && item.generator !== attemptControls.attemptGenerator.value) return false;
      if (attemptControls.promptDiff.value === "different" && item.submitted_prompt_differs_from_compiled !== true) return false;
      if (attemptControls.promptDiff.value === "same" && item.submitted_prompt_differs_from_compiled !== false) return false;
      if (attemptControls.promptDiff.value === "unknown" && item.submitted_prompt_differs_from_compiled != null) return false;
      if (attemptControls.submissionState.value === "tracked" && !item.submission_tracked) return false;
      if (attemptControls.submissionState.value === "untracked" && item.submission_tracked) return false;
      if (attemptControls.attemptReference.value && !(item.reference_item_ids||[]).includes(attemptControls.attemptReference.value)) return false;
      if (attemptControls.attemptProvenance.value === "complete" && (item.legacy_fallback || item.incomplete_provenance)) return false;
      if (attemptControls.attemptProvenance.value === "legacy" && !item.legacy_fallback) return false;
      if (attemptControls.attemptProvenance.value === "incomplete" && !item.incomplete_provenance) return false;
      if (attemptControls.retryExhausted.checked && !item.transport_retry_exhausted) return false;
      if (attemptControls.boundedRepair.checked && !item.has_later_bounded_repair) return false;
      return true;
    }
    function renderAttempts() {
      const visible=attemptState.cases.filter(attemptMatches);
      document.getElementById("attemptGrid").innerHTML=visible.map(item=>`
        <article class="card">
          <div class="thumb">${item.thumbnail ? `<img src="${esc(item.thumbnail)}" alt="${esc(item.case_id)}" loading="lazy">` : `<div class="placeholder ${item.output_error ? "error" : ""}">${esc(item.output_error || (item.generated_status === "error" ? "Generation error · no output" : "No output recorded"))}</div>`}</div>
          <div class="card-body"><div class="eyebrow">${esc(item.generated_status)} → ${esc(item.effective_status)}${item.archived ? " · archived" : ""}</div><h2 class="item-id">${esc(item.case_id)}</h2><p class="path">${esc(item.request || "No request snapshot")}</p>
          ${chips([item.intent,item.medium,...(item.characters||[]),...(item.forms||[]),item.shot,item.view_angle].filter(Boolean).slice(0,10))}
          <div class="outcome"><span>refs ${item.reference_count}</span><span>${esc(item.generator||"unknown generator")}</span><span>${item.duration_seconds == null ? "no timing" : `${esc(item.duration_seconds)}s`}</span></div>
          <dl class="card-facts"><dt>Prompt hashes</dt><dd>compiled ${esc(item.compiled_prompt_sha256||"—")}<br>submitted ${esc(item.submitted_prompt_sha256||"—")}<br>different=${esc(item.submitted_prompt_differs_from_compiled ?? "—")}</dd><dt>Prompt report</dt><dd>${esc(item.prompt_length ?? "—")} chars · ${item.prompt_compile ? "available" : "unavailable"}</dd><dt>Reference IDs</dt><dd>${esc((item.reference_item_ids||[]).join(", ")||"—")}</dd><dt>Preview checks</dt><dd>${esc(checkSummary(item.preview_checks))}</dd><dt>Medium checks</dt><dd>${esc(checkSummary(item.medium_component_checks))}</dd><dt>Transport</dt><dd>network=${esc(item.network_failure ?? "—")} · exhausted=${esc(item.transport_retry_exhausted ?? "—")}</dd></dl>
          ${item.failure_categories?.length ? `<p class="path error">${esc(item.failure_categories.join(" · "))}</p>` : ""}
          ${item.user_feedback?.length ? `<p class="path">反馈：${esc(item.user_feedback.join("；"))}</p>` : ""}
          <button type="button" data-attempt-detail="${esc(item.case_id)}">查看详情</button></div>
        </article>`).join("");
      document.getElementById("attemptEmpty").hidden=visible.length!==0;
      document.getElementById("attemptStatus").textContent=`显示 ${visible.length} / ${attemptState.cases.length} 个生成 case；decision attempt 不另计生成`;
    }
    function jsonBlock(label, value) { return value == null ? "" : `<section class="detail-section"><h3>${esc(label)}</h3><pre>${esc(JSON.stringify(value,null,2))}</pre></section>`; }
    function showAttemptDetail(item) {
      attemptState.current=item;
      document.getElementById("attemptDetailTitle").textContent=item.case_id;
      const inputHtml=(item.actual_input_images||[]).map(input=>`<article class="input-item">${input.image_url ? `<img src="${esc(input.image_url)}" alt="input ${esc(input.order)} ${esc(input.role)}">` : ""}<strong>Input ${esc(input.order)} · ${esc(input.role)}</strong><p class="path">${esc(input.source_path||input.path||"")}</p><p class="path">${esc(input.sha256||"")}</p></article>`).join("");
      document.getElementById("attemptDetailBody").innerHTML=`
        ${item.output_url && !item.output_error ? `<img class="detail-image" src="${esc(item.output_url)}" alt="${esc(item.case_id)} full output">` : `<div class="state ${item.output_error ? "error" : ""}">${esc(item.output_error || "No visual output")}</div>`}
        <dl><dt>Task / generation</dt><dd>${esc(item.task_id)} / ${esc(item.generation_attempt)}</dd><dt>Generated / effective</dt><dd>${esc(item.generated_status)} / ${esc(item.effective_status)}</dd><dt>Decision attempt</dt><dd>${esc(item.decision_attempt ?? "—")}</dd><dt>Intent / medium</dt><dd>${esc(item.intent)} / ${esc(item.medium)}</dd><dt>Character forms</dt><dd>${esc(JSON.stringify(item.identity_forms))}</dd><dt>Shot / view</dt><dd>${esc(item.shot||"—")} / ${esc(item.view_angle||"—")}</dd><dt>Generator / timing</dt><dd>${esc(item.generator||"—")} / ${esc(item.duration_seconds ?? "—")}s</dd><dt>Transport</dt><dd>${esc(item.generation_transport||"—")}; tracked=${esc(item.submission_tracked)}; network=${esc(item.network_failure)}; exhausted=${esc(item.transport_retry_exhausted)}</dd><dt>Prompt hashes</dt><dd>compiled ${esc(item.compiled_prompt_sha256||"—")}<br>submitted ${esc(item.submitted_prompt_sha256||"—")}<br>different=${esc(item.submitted_prompt_differs_from_compiled)}</dd><dt>Prompt length / report</dt><dd>${esc(item.prompt_length ?? "—")} / ${item.prompt_compile ? "available" : "unavailable"}</dd><dt>References</dt><dd>${esc((item.reference_item_ids||[]).join(", ")||"—")}</dd><dt>Parent / children</dt><dd>${esc(item.parent_task_id||"—")} / ${esc((item.child_tasks||[]).join(", ")||"—")}</dd><dt>Later bounded repair</dt><dd>${esc((item.later_bounded_repairs||[]).join(", ")||"—")}</dd><dt>Provenance</dt><dd>${esc(JSON.stringify(item.provenance))}</dd></dl>
        <section class="detail-section"><h3>Request</h3><pre>${esc(item.request||"")}</pre></section>
        ${inputHtml ? `<section class="detail-section"><h3>Ordered submitted inputs</h3><div class="input-list">${inputHtml}</div></section>` : ""}
        ${jsonBlock("Preview checks",item.preview_checks)}${jsonBlock("Medium component checks",item.medium_component_checks)}${jsonBlock("Full QA",item.qa)}${jsonBlock("Structured failures",item.failures)}${jsonBlock("Decision chain",item.decision_chain)}${jsonBlock("User feedback",item.user_feedback)}${jsonBlock("Reference manifest",item.reference_manifest)}${jsonBlock("Prompt compilation report",item.prompt_compile)}
        ${item.compiled_prompt != null ? `<section class="detail-section"><h3>Compiled prompt</h3><pre>${esc(item.compiled_prompt)}</pre></section>` : ""}
        ${item.submitted_prompt != null ? `<section class="detail-section"><h3>Exact submitted prompt</h3><pre>${esc(item.submitted_prompt)}</pre></section>` : ""}`;
      document.getElementById("attemptDetail").showModal();
    }
    document.getElementById("attemptGrid").addEventListener("click",event=>{const button=event.target.closest("[data-attempt-detail]"); if(button) showAttemptDetail(attemptState.byId.get(button.dataset.attemptDetail));});
    document.getElementById("closeAttemptDetail").addEventListener("click",()=>document.getElementById("attemptDetail").close());
    document.getElementById("attemptDetail").addEventListener("click",event=>{if(event.target===event.currentTarget) event.currentTarget.close();});
    for (const control of Object.values(attemptControls)) control.addEventListener(control.type === "search" ? "input" : "change",renderAttempts);
    document.getElementById("clearAttempts").addEventListener("click",()=>{for(const control of Object.values(attemptControls)){if(control.type==="checkbox") control.checked=false; else control.value=control.id==="caseType"?"generation":"";} renderAttempts(); attemptControls.attemptSearch.focus();});

    fetch("attempts.json").then(response=>{if(!response.ok) throw new Error(`HTTP ${response.status}`); return response.json();}).then(data=>{
      if(!Array.isArray(data.cases)) throw new Error("attempts.json 缺少 cases 数组");
      attemptState.cases=data.cases; attemptState.byId=new Map(data.cases.map(item=>[item.case_id,item]));
      const add=(id,values)=>document.getElementById(id).insertAdjacentHTML("beforeend",values.map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join(""));
      add("attemptCharacter",attemptUnique("characters",true)); add("attemptForm",attemptUnique("forms",true)); add("attemptShot",attemptUnique("shot")); add("attemptView",attemptUnique("view_angle")); add("attemptFailure",attemptUnique("failure_categories",true)); add("attemptGenerator",attemptUnique("generator")); add("attemptReference",attemptUnique("reference_item_ids",true));
      for(const control of Object.values(attemptControls)) control.disabled=false; document.getElementById("clearAttempts").disabled=false; document.getElementById("attemptLoading").hidden=true; renderAttempts();
    }).catch(error=>{document.getElementById("attemptLoading").hidden=true; const box=document.getElementById("attemptError"); box.hidden=false; box.textContent=`无法读取 attempts.json：${error.message}。请重新运行 builder 并使用 --serve。`; document.getElementById("attemptStatus").textContent="加载失败";});

    fetch("summary.json").then(response=>{if(!response.ok) throw new Error(`HTTP ${response.status}`); return response.json();}).then(data=>{
      const duration=data.duration_coverage||{}, transport=data.generation_transport||{}, overhead=data.workflow_overhead||{};
      const cards=[
        ["Recorded attempts",data.total_attempts,`accepted ${data.accepted_attempts} · rejected ${data.rejected_attempts} · candidate ${data.candidate_attempts} · error ${data.error_attempts}`],
        ["Accepted yield",data.accepted_yield,"Decided attempt rows; descriptive only"],
        ["Generation timing",duration.median_seconds == null ? "n/a" : `${duration.median_seconds}s`,`recorded ${duration.recorded}/${duration.total} · p90 ${duration.p90_seconds ?? "n/a"}s`],
        ["Tracked submissions",transport.tracked_submissions ?? 0,`untracked remote ${transport.untracked_remote_attempts ?? 0}`],
        ["Retry exhausted",transport.transport_retry_exhausted_errors ?? 0,"Network transport exhaustion"],
        ["Controllable overhead",overhead.combined?.median_seconds == null ? "n/a" : `${overhead.combined.median_seconds}s`,`pre median ${overhead.pre_generation?.median_seconds ?? "n/a"}s · post median ${overhead.post_generation?.median_seconds ?? "n/a"}s`]
      ];
      document.getElementById("summaryGrid").innerHTML=cards.map(([title,value,note])=>`<article class="summary-card"><h2>${esc(title)}</h2><strong>${esc(value)}</strong><p>${esc(note)}</p></article>`).join("")+jsonBlock("Failure categories",data.failure_categories)+jsonBlock("Generation transport by semantic intent",transport.by_semantic_intent)+jsonBlock("Repeated error tasks",data.repeated_error_tasks);
      document.getElementById("summaryLoading").hidden=true; document.getElementById("summaryStatus").textContent="来源：reference_feedback_report.py；仅描述，不自动修改检索、prompt 或偏好。";
    }).catch(error=>{document.getElementById("summaryLoading").hidden=true; const box=document.getElementById("summaryError"); box.hidden=false; box.textContent=`无法读取 summary.json：${error.message}`; document.getElementById("summaryStatus").textContent="加载失败";});

    fetch("references.json").then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); }).then(data => {
      if (!Array.isArray(data.items)) throw new Error("references.json 缺少 items 数组");
      state.items=data.items; state.byId=new Map(data.items.map(item=>[item.item_id,item])); state.queryContext=data.query_context;
      populate("subject",unique(data.items,"subjects")); populate("form",unique(data.items,"forms")); populate("shot",unique(data.items,"shot_types")); populate("view",unique(data.items,"view_angles")); populate("sceneId",unique(data.items,"scene_ids")); populate("sceneEconomy",unique(data.items,"scene_economy")); populate("blackMass",unique(data.items,"black_mass")); populate("tone",unique(data.items,"tone_density")); populate("falloff",unique(data.items,"detail_falloff")); populate("role",unique(data.items,"eligible_roles"));
      for (const control of Object.values(controls)) control.disabled=false; document.getElementById("clear").disabled=false; document.getElementById("loading").hidden=true;
      if (data.query_context) { document.getElementById("queryOnlyRow").hidden=false; document.getElementById("queryContext").textContent=`检索结果 ${data.query_result_count} 项`; }
      else controls.queryOnly.checked=false;
      const params=new URLSearchParams(location.search); for (const [id,control] of Object.entries(controls)) { if (!params.has(id) || (id === "queryOnly" && !data.query_context)) continue; if (control.type === "checkbox") control.checked=params.get(id)==="1"; else if ([...control.options].some(option=>option.value===params.get(id)) || id==="search") control.value=params.get(id); }
      render();
    }).catch(error => { document.getElementById("loading").hidden=true; const box=document.getElementById("error"); box.hidden=false; box.textContent=`无法读取 references.json：${error.message}。请用 builder 的 --serve 模式打开。`; document.getElementById("status").textContent="加载失败"; });
  </script>
</body>
</html>
'''


def build(config: dict, root: Path, query_results: Path | None) -> dict:
    gallery = root / "gallery"
    ensure_safe_output(gallery, config)
    gallery.mkdir(parents=True, exist_ok=True)
    payload = read_references(config, root, gallery, query_results)
    attempts = read_attempts(config, root, gallery)
    summary = read_summary(root)
    atomic_write_json(gallery / "references.json", payload)
    atomic_write_json(gallery / "attempts.json", attempts)
    atomic_write_json(gallery / "summary.json", summary)
    atomic_write_text(gallery / "index.html", HTML)
    serve_command = [
        "scripts/run-python",
        "scripts/build_workflow_gallery.py",
        "--workflow-root",
        str(root),
    ]
    if query_results is not None:
        serve_command += [
            "--query-results",
            str(query_results.expanduser().resolve()),
        ]
    serve_command.append("--serve")
    return {
        "gallery": str(gallery / "index.html"),
        "references": payload["count"],
        "attempts": attempts["count"],
        "attempt_errors": attempts["error_count"],
        "attempt_data_errors": len(attempts["errors"]),
        "thumbnail_errors": len(payload["errors"]),
        "query_results": payload["query_result_count"],
        "serve_command": shlex.join(serve_command),
    }


def serve(root: Path, port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
        *args, directory=str(root), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Serving http://127.0.0.1:{port}/gallery/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    args = parse_args()
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    try:
        result = build(config, root, args.query_results)
        print(
            json.dumps(result, ensure_ascii=False, indent=2)
            if args.json
            else result["gallery"]
        )
        if args.serve:
            serve(root, args.port)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
