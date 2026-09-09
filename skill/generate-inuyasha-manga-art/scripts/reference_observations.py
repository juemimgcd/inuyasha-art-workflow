#!/usr/bin/env python3
"""Store inspected image regions and search their evidence without changing catalog ranking."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from PIL import Image

from composite_local_microfix import valid_box
from structure_review import file_hash, load
from workflow_common import (
    VIEW_ANGLE_VALUES, eligible_character_style_candidate, load_config,
    now_iso, open_database, workflow_paths, workflow_root,
)

SCOPES = ("construction", "form", "character-rendering", "scene-rendering")


def pair(value: str) -> tuple[str, str]:
    subject, separator, form = value.partition("=")
    if not separator or not subject.strip() or not form.strip():
        raise argparse.ArgumentTypeError("subject-form must look like SUBJECT=FORM")
    return subject.strip(), form.strip()


def box(value: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("region must be X,Y,WIDTH,HEIGHT") from exc
    if len(values) != 4:
        raise argparse.ArgumentTypeError("region must be X,Y,WIDTH,HEIGHT")
    return values


def scope_allowed(entry: dict, scope: str) -> bool:
    if scope == "construction":
        return entry.get("role") == "identity" and entry.get("source_id") != "user-supplied"
    if scope == "form":
        return entry.get("role") in {"identity", "form"}
    return entry.get("role") == "style" and entry.get("style_scope") == (
        "character" if scope == "character-rendering" else "scene"
    )


def record(root: Path, args: argparse.Namespace) -> dict:
    task = args.task_dir.expanduser().resolve()
    manifest = load(task / "reference-manifest.json")
    entries = [entry for entry in manifest.get("references", []) if entry.get("item_id") == args.item_id]
    if len(entries) != 1:
        raise ValueError("item must resolve to exactly one selected manifest reference")
    entry = entries[0]
    if not scope_allowed(entry, args.scope):
        raise ValueError("observation scope exceeds this selected reference's authority")
    path = Path(entry.get("rendered_path") or entry.get("original_path") or "").expanduser().resolve()
    original = Path(entry.get("original_path") or path).expanduser().resolve()
    with Image.open(path) as image:
        if not valid_box(args.region, image.size):
            raise ValueError("region must locate an in-bounds visible detail in the rendered reference")
        size = list(image.size)
    if not args.detail.strip():
        raise ValueError("detail must describe an actually inspected visible relationship")
    visible_forms = dict(args.subject_form)
    if not visible_forms and args.scope != "scene-rendering":
        if len(entry.get("subject_forms", {})) != 1:
            raise ValueError("multi-subject regions require explicit visible --subject-form entries")
        subject, forms = next(iter(entry["subject_forms"].items()))
        if len(forms) != 1:
            raise ValueError("region form is ambiguous; supply exact --subject-form")
        visible_forms = {subject: forms[0]}
    if any(form not in entry.get("subject_forms", {}).get(subject, []) for subject, form in visible_forms.items()):
        raise ValueError("visible subject/form must be supported by the selected reference")
    observation = {
        "schema_version": 1, "recorded_at": now_iso(), "task_dir": str(task),
        "item_id": args.item_id, "source_id": entry.get("source_id"),
        "reference_domain": entry.get("reference_domain"), "role": entry.get("role"),
        "style_scope": entry.get("style_scope"), "scope": args.scope,
        "subject_forms": entry.get("subject_forms", {}), "subjects": entry.get("subjects", []),
        "visible_subject_forms": visible_forms,
        "path": str(path), "sha256": file_hash(path), "size": size,
        "original_path": str(original), "original_sha256": file_hash(original),
        "region": list(args.region), "view_angle": args.view_angle,
        "detail": args.detail.strip(), "tags": sorted(set(tag.strip() for tag in args.tag if tag.strip())),
        "evidence_kind": "human-or-agent-visual-inspection",
    }
    encoded = (json.dumps(observation, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    folder = root / "reference-observations"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{hashlib.sha256(encoded).hexdigest()}.json"
    with destination.open("xb") as handle:
        handle.write(encoded)
    return {"observation": str(destination), "item_id": args.item_id, "catalog_changed": False}


def search(root: Path, args: argparse.Namespace) -> dict:
    if args.scope != "scene-rendering" and not args.subject_form:
        raise ValueError("exact --subject-form is required for character or prop evidence")
    database = workflow_paths(root)["database"]
    connection = open_database(database, read_only=True)
    try:
        catalog = {row["item_id"]: dict(row) for row in connection.execute(
            "SELECT item_id, source_id, content_hash, subjects, subject_forms, reference_domain FROM items"
        )}
    finally:
        connection.close()
    requested = dict(args.subject_form)
    if len(requested) != len(args.subject_form):
        raise ValueError("specify one exact form per subject")
    queries = [query.strip().casefold() for query in args.detail if query.strip()]
    matches = []
    stale = []
    view_gaps = set()
    seen = set()
    for record_path in sorted((root / "reference-observations").glob("*.json")):
        try:
            row = load(record_path)
        except (OSError, ValueError) as exc:
            stale.append({"record": str(record_path), "reason": f"unreadable: {exc}"})
            continue
        if file_hash(record_path) != record_path.stem or type(row.get("schema_version")) is not int or row["schema_version"] != 1:
            stale.append({"record": str(record_path), "reason": "record hash or schema changed"})
            continue
        if row.get("scope") != args.scope:
            continue
        current = catalog.get(row.get("item_id"))
        if current is None:
            stale.append({"record": str(record_path), "reason": "item absent from current catalog"})
            continue
        for name in ("subjects", "subject_forms"):
            current[name] = json.loads(current[name]) if isinstance(current[name], str) else current[name]
        if args.scope in {"character-rendering", "scene-rendering"} and current["source_id"] != f"{args.medium}-curated":
            continue
        if args.scope == "character-rendering" and not eligible_character_style_candidate(current, args.subject_form):
            continue
        visible_forms = row.get("visible_subject_forms")
        if visible_forms is None and len(row.get("subject_forms", {})) == 1:
            visible_forms = {subject: forms[0] for subject, forms in row["subject_forms"].items() if len(forms) == 1}
        covered = [subject for subject, form in requested.items()
                   if form in current["subject_forms"].get(subject, [])
                   and (visible_forms or {}).get(subject) == form]
        if requested and not covered:
            continue
        if (current["subject_forms"] != row.get("subject_forms")
                or current["reference_domain"] != row.get("reference_domain")
                or current["source_id"] != row.get("source_id")
                or not scope_allowed(row, args.scope)):
            stale.append({"record": str(record_path), "reason": "catalog authority or subject/form changed"})
            continue
        if current.get("content_hash") and current["content_hash"] != row.get("original_sha256"):
            stale.append({"record": str(record_path), "reason": "catalog content hash changed"})
            continue
        path = Path(row.get("path") or "")
        original = Path(row.get("original_path") or "")
        if not path.is_file() or not original.is_file() or file_hash(path) != row.get("sha256") or file_hash(original) != row.get("original_sha256"):
            stale.append({"record": str(record_path), "reason": "image bytes changed or unavailable"})
            continue
        haystack = " ".join([row.get("detail", ""), *row.get("tags", [])]).casefold()
        if not all(query in haystack for query in queries):
            continue
        if args.view_angle and row.get("view_angle") != args.view_angle:
            view_gaps.update(covered)
            continue
        key = (row["item_id"], row["sha256"], tuple(row["region"]), row["detail"])
        if key in seen:
            continue
        seen.add(key)
        matches.append({**row, "record": str(record_path), "covered_subjects": covered})
    groups = {}
    for subject in requested or {"scene": ""}:
        rows = [row for row in matches if subject == "scene" or subject in row["covered_subjects"]]
        groups[subject] = {
            "status": "HIT" if rows else "INSUFFICIENT_VIEW" if subject in view_gaps else "MISS",
            "inspected_region_matches": len(rows), "records": rows[:args.limit],
            "next_step": (
                "Inspect the region against the current request before selecting any reference."
                if rows else "Inspect or annotate up to four already-retrieved exact-form candidates; record insufficiency if no valid view exists. Do not relax character, form, or medium."
            ),
        }
    return {
        "schema_version": 1, "mode": "inspected-evidence-search",
        "query": queries, "groups": groups, "stale_records": stale,
        "catalog_ranking_changed": False, "automatic_selection": False,
        "note": "Region observations are visual evidence notes, not automatic vision or permission to reuse pose/composition. Missing annotations are not proof that the library lacks a suitable image.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("record")
    add.add_argument("--task-dir", type=Path, required=True)
    add.add_argument("--item-id", required=True)
    add.add_argument("--scope", choices=SCOPES, required=True)
    add.add_argument("--region", type=box, required=True)
    add.add_argument("--detail", required=True)
    add.add_argument("--tag", action="append", default=[])
    add.add_argument("--subject-form", type=pair, action="append", default=[])
    add.add_argument("--view-angle", choices=VIEW_ANGLE_VALUES)
    query = commands.add_parser("search")
    query.add_argument("--scope", choices=SCOPES, required=True)
    query.add_argument("--subject-form", type=pair, action="append", default=[])
    query.add_argument("--medium", choices=("manga", "tv"), default="manga")
    query.add_argument("--detail", action="append", default=[])
    query.add_argument("--view-angle", choices=VIEW_ANGLE_VALUES)
    query.add_argument("--limit", type=int, default=4, choices=range(1, 5))
    args = parser.parse_args()
    try:
        root = workflow_root(load_config(), args.workflow_root)
        result = record(root, args) if args.command == "record" else search(root, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        parser.exit(2, f"Reference observation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
