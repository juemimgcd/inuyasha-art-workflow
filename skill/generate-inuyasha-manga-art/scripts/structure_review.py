#!/usr/bin/env python3
"""Bind shot-specific construction checks and protected regions to one output."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

from composite_local_microfix import valid_box
from workflow_common import atomic_write_json


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return data


def required_checks(brief: dict) -> list[tuple[str, str]]:
    rows = [
        (entry["subject"], feature)
        for entry in brief.get("official_facet_requirements", [])
        for feature in entry.get("required", [])
    ]
    covered = {subject for subject, _ in rows}
    for subject in brief.get("identity_forms", {}):
        if subject not in covered:
            rows.extend((subject, feature) for feature in ("face", "hair-ear", "costume"))
    for subject in brief.get("prop_forms", {}):
        if subject not in {name for name, _ in rows}:
            rows.append((subject, "construction"))
    return list(dict.fromkeys(rows))


def reference_options(manifest: dict) -> list[dict]:
    options = []
    for entry in manifest.get("references", []):
        if entry.get("role") not in {"identity", "form", "target"}:
            continue
        path = Path(entry.get("rendered_path") or entry.get("original_path") or "")
        if path.is_file():
            options.append({
                "item_id": entry.get("item_id"), "role": entry.get("role"),
                "path": str(path), "sha256": file_hash(path),
                "subjects": entry.get("subjects", []),
                "subject_forms": entry.get("subject_forms", {}),
            })
    return options


def review_template(task: Path, output: Path) -> dict:
    brief = load(task / "brief.json")
    manifest = load(task / "reference-manifest.json")
    with Image.open(output) as image:
        size = list(image.size)
    return {
        "schema_version": 1,
        "purpose": "post-generation construction audit; never generator input",
        "brief_sha256": file_hash(task / "brief.json"),
        "reference_manifest_sha256": file_hash(task / "reference-manifest.json"),
        "output_sha256": file_hash(output), "output_size": size,
        "shot": brief.get("shot"), "view_angle": brief.get("view_angle"),
        "reference_options": reference_options(manifest),
        "checks": [
            {"subject": subject, "feature": feature, "visibility": "pending",
             "expected": "", "reference_item_id": "", "reference_sha256": "",
             "reference_box": None, "output_box": None, "result": "pending", "note": ""}
            for subject, feature in required_checks(brief)
        ],
        "protected_regions": [],
    }


def review_failures(task: Path, output: Path | None, review_path: Path) -> list[str]:
    try:
        return _review_failures(task, output, load(review_path))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return [f"structure review is unreadable or malformed: {exc}"]


def _review_failures(task: Path, output: Path | None, review: dict) -> list[str]:
    failures = []
    if output is None or not output.is_file():
        return ["structure review requires an existing output"]
    brief = load(task / "brief.json")
    manifest = load(task / "reference-manifest.json")
    if type(review.get("schema_version")) is not int or review["schema_version"] != 1:
        failures.append("unsupported structure review schema")
    for key, path in (("brief_sha256", task / "brief.json"),
                      ("reference_manifest_sha256", task / "reference-manifest.json"),
                      ("output_sha256", output)):
        if review.get(key) != file_hash(path):
            failures.append(f"structure review {key} is stale")
    if review.get("shot") != brief.get("shot") or review.get("view_angle") != brief.get("view_angle"):
        failures.append("structure review belongs to a different shot or view")
    with Image.open(output) as image:
        output_size = image.size
    if review.get("output_size") != list(output_size):
        failures.append("structure review output dimensions are stale")
    checks = review.get("checks")
    if not isinstance(checks, list) or any(not isinstance(row, dict) for row in checks):
        return failures + ["structure checks must be a list of objects"]
    required = set(required_checks(brief))
    keys = [(row.get("subject"), row.get("feature")) for row in checks]
    if set(keys) != required or len(keys) != len(set(keys)):
        failures.append("structure checks must cover every shot-specific subject/facet exactly once")
    options = {row["item_id"]: row for row in reference_options(manifest)}
    for row in checks:
        label = f"{row.get('subject')}/{row.get('feature')}"
        if not str(row.get("note") or "").strip():
            failures.append(f"{label}: concrete visual evidence note required")
        if row.get("visibility") == "not-visible":
            if row.get("result") != "n/a":
                failures.append(f"{label}: not-visible must use n/a with an occlusion/crop reason")
            continue
        if row.get("visibility") != "visible" or row.get("result") != "pass":
            failures.append(f"{label}: visible construction must pass before handoff")
        if not str(row.get("expected") or "").strip():
            failures.append(f"{label}: name the observed construction, layers, or attachment")
        if not valid_box(row.get("output_box") or (), output_size):
            failures.append(f"{label}: output_box must locate the visible evidence")
        reference = options.get(row.get("reference_item_id"))
        if reference is None:
            failures.append(f"{label}: missing selected identity or target authority")
            continue
        if reference["role"] == "form" and row.get("feature") != "form":
            failures.append(f"{label}: form fallback cannot supply canonical construction")
        if reference["role"] != "target":
            subject = row.get("subject")
            form = (brief.get("identity_forms", {}) | brief.get("prop_forms", {})).get(subject)
            if subject not in reference["subjects"] or (form and form not in reference["subject_forms"].get(subject, [])):
                failures.append(f"{label}: reference does not cover the exact subject and form")
        if row.get("reference_sha256") != reference["sha256"]:
            failures.append(f"{label}: reference hash is stale")
        with Image.open(reference["path"]) as image:
            if not valid_box(row.get("reference_box") or (), image.size):
                failures.append(f"{label}: reference_box must locate the source construction")
    regions = review.get("protected_regions", [])
    if not isinstance(regions, list) or any(not isinstance(row, dict) for row in regions):
        return failures + ["protected_regions must be a list of named boxes"]
    if regions:
        target = (brief.get("local_edit") or {}).get("target")
        if not target:
            target = next((row.get("original_path") or row.get("rendered_path")
                           for row in manifest.get("references", []) if row.get("role") == "target"), None)
        if not target or not Path(target).is_file():
            return failures + ["protected regions require the original target"]
        if review.get("protected_target_sha256") != file_hash(Path(target)):
            failures.append("protected target hash is missing or stale")
        with Image.open(target) as source_image, Image.open(output) as output_image:
            source = source_image.convert("RGBA")
            candidate = output_image.convert("RGBA")
            if source.size != candidate.size:
                return failures + ["protected regions require unchanged canvas dimensions"]
            for region in regions:
                box = region.get("box") or ()
                if not str(region.get("name") or "").strip() or not valid_box(box, source.size):
                    failures.append("each protected region needs a name and an in-bounds box")
                    continue
                x, y, width, height = box
                bounds = (x, y, x + width, y + height)
                diff = ImageChops.difference(source.crop(bounds), candidate.crop(bounds))
                if any(channel.getbbox() is not None for channel in diff.split()):
                    failures.append(f"protected region changed: {region['name']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check"))
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    task = args.task_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    review = args.review.expanduser().resolve() if args.review else task / "structure-review.json"
    try:
        if args.command == "prepare":
            if review.exists():
                parser.error("review already exists; use a new --review path for another output")
            atomic_write_json(review, review_template(task, output))
            print(json.dumps({"review": str(review), "state": "pending-visual-inspection"}))
            return 0
        failures = review_failures(task, output, review)
        print(json.dumps({"ok": not failures, "failures": failures}, ensure_ascii=False, indent=2))
        return 2 if failures else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Structure review failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
