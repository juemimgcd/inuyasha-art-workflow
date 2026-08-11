#!/usr/bin/env python3
"""Validate the skill, growing curated libraries, catalog, and helper runtime."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from build_reference_index import freshness
from workflow_common import (
    CONFIG_PATH,
    SKILL_DIR,
    load_config,
    library_signature,
    workflow_paths,
    workflow_root,
)

REQUIRED_FILES = (
    "SKILL.md",
    "references/source-map.md",
    "references/source-library.json",
    "references/workflow-contract.md",
    "references/quality-gate.md",
    "references/identity-ledgers.json",
    "references/visual-traits.md",
    "scripts/build_reference_index.py",
    "scripts/search_reference_index.py",
    "scripts/browse_curated_styles.py",
    "scripts/init_art_task.py",
    "scripts/prepare_reference_set.py",
    "scripts/validate_art_task.py",
    "scripts/task_workflow.py",
    "scripts/plan_art_task.py",
    "scripts/continue_art_task.py",
    "scripts/compile_prompt.py",
    "scripts/record_attempt.py",
    "scripts/coverage_report.py",
    "scripts/reference_feedback_report.py",
    "scripts/preference_profile.py",
    "scripts/validate_all_tasks.py",
    "scripts/migrate_art_tasks.py",
    "scripts/archive_art_task.py",
)
EXPECTED_CATALOG_SCHEMA = "5"


def main() -> int:
    failures = []
    for relative in REQUIRED_FILES:
        path = SKILL_DIR / relative
        if not path.is_file():
            failures.append(f"missing required file: {path}")

    config = load_config(CONFIG_PATH)
    identity_ledgers = json.loads(
        (SKILL_DIR / "references/identity-ledgers.json").read_text(encoding="utf-8")
    )
    if identity_ledgers.get("schema_version") != 1:
        failures.append("identity-ledgers.json must use schema 1")
    if "犬夜叉" not in identity_ledgers.get("characters", {}):
        failures.append("identity-ledgers.json must include 犬夜叉")
    for source in config["sources"]:
        path = Path(source["path"])
        if not path.is_dir():
            failures.append(f"missing source directory: {path}")
        if source["id"] in ("manga-curated", "tv-curated", "selected-output"):
            policy = source.get("metadata_policy", {})
            expected_primary = (
                "structured-filenames"
                if source["id"] == "selected-output"
                else "folder-names"
            )
            if policy.get("primary") != expected_primary:
                failures.append(f"{source['id']} must use {expected_primary} metadata")
            if policy.get("content_label") != "leaf-folder":
                failures.append(f"{source['id']} must use leaf-folder content labels")
            naming_guide = path / "命名规则.md"
            if not naming_guide.is_file():
                failures.append(f"missing naming guide: {naming_guide}")
        roles = set(source.get("evidence_roles", []))
        if source["id"] in {"manga-curated", "tv-curated"}:
            if not {"rendering", "content"}.issubset(roles):
                failures.append(
                    f"{source['id']} must declare rendering and content evidence roles"
                )
        if source["id"] == "official" and "identity" not in roles:
            failures.append("official must declare identity evidence authority")
    source_ids = {source["id"] for source in config["sources"]}
    for source_id in ("official", "manga-curated", "tv-curated", "selected-output"):
        if source_id not in source_ids:
            failures.append(f"missing required source: {source_id}")
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        failures.append("Pillow unavailable; use scripts/run-python")

    root = workflow_root(config)
    paths = workflow_paths(root)
    database = paths["database"]
    counts = {}
    curated_counts = {}
    location_count = 0
    alias_count = 0
    if not database.is_file():
        failures.append(f"catalog missing: {database}")
    else:
        fresh, reason = freshness(
            database, config, library_signature(config), paths["annotations"]
        )
        if not fresh:
            failures.append(f"catalog is stale: {reason}")
        try:
            connection = sqlite3.connect(database)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            meta = dict(connection.execute("SELECT key, value FROM meta"))
            if meta.get("schema_version") != EXPECTED_CATALOG_SCHEMA:
                failures.append(
                    "catalog schema must be rebuilt for folder-aware indexing"
                )
            item_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(items)")
            }
            required_columns = {
                "content_hash",
                "folder_path",
                "content_label",
                "folder_tags",
                "subjects",
                "forms",
                "subject_forms",
                "shot_types",
                "filename_terms",
                "duplicate_count",
            }
            missing_columns = required_columns - item_columns
            if missing_columns:
                failures.append(
                    f"catalog missing folder-aware columns: {sorted(missing_columns)}"
                )
            else:
                form_rows = {
                    row[0]: json.loads(row[1])
                    for row in connection.execute(
                        "SELECT relative_path, forms FROM items "
                        "WHERE source_id = 'official' AND relative_path IN (?, ?)",
                        (
                            "犬夜叉设定集/犬夜叉人类形态图01.jpg",
                            "犬夜叉设定集/犬夜叉全身图带铁碎牙01.jpg",
                        ),
                    )
                }
                if form_rows.get("犬夜叉设定集/犬夜叉人类形态图01.jpg") != [
                    "human-form"
                ]:
                    failures.append("official human-form sheet is not indexed exactly")
                if form_rows.get("犬夜叉设定集/犬夜叉全身图带铁碎牙01.jpg") != [
                    "half-demon-form"
                ]:
                    failures.append("Tessaiga full-body sheet must be half-demon-form")
                kagome_default = connection.execute(
                    """
                    SELECT COUNT(*) FROM items
                    WHERE source_id = 'official'
                      AND EXISTS (
                        SELECT 1 FROM json_each(subject_forms) AS subject_form
                        JOIN json_each(subject_form.value) AS compatible_form
                        WHERE subject_form.key = '戈薇'
                          AND compatible_form.value = 'default-form'
                      )
                    """
                ).fetchone()[0]
                if kagome_default == 0:
                    failures.append(
                        "official Kagome sheets have no default-form metadata"
                    )
                leaked_grandpa = connection.execute(
                    """
                    SELECT COUNT(*) FROM items
                    WHERE source_id = 'official'
                      AND relative_path LIKE '戈薇爷爷设定集/%'
                      AND EXISTS (SELECT 1 FROM json_each(subjects) WHERE value = '戈薇')
                    """
                ).fetchone()[0]
                if leaked_grandpa:
                    failures.append("Kagome leaked into Grandpa Higurashi metadata")
                metadata_rows = connection.execute(
                    "SELECT item_id, subjects, forms, subject_forms, shot_types, tags "
                    "FROM items WHERE kind = 'image'"
                ).fetchall()
                for item_id, subjects_json, forms_json, subject_forms_json, shots_json, tags_json in metadata_rows:
                    subjects = set(json.loads(subjects_json or "[]"))
                    forms = set(json.loads(forms_json or "[]"))
                    subject_forms = json.loads(subject_forms_json or "{}")
                    paired_forms = {
                        form
                        for compatible in subject_forms.values()
                        for form in compatible
                    }
                    if subjects and set(subject_forms) != subjects:
                        failures.append(
                            f"subject_forms keys do not match subjects: {item_id}"
                        )
                    if subjects and paired_forms != forms:
                        failures.append(
                            f"flat forms do not match subject_forms union: {item_id}"
                        )
                    tags = set(json.loads(tags_json or "[]"))
                    shots = set(json.loads(shots_json or "[]"))
                    if (
                        {"view-angle:back", "suitable-for:back-view"} & tags
                        and "back-view" not in shots
                    ):
                        failures.append(
                            f"back-view annotation was not promoted to shot facet: {item_id}"
                        )
            location_table = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='item_locations'"
            ).fetchone()
            if location_table:
                location_count = connection.execute(
                    "SELECT COUNT(*) FROM item_locations"
                ).fetchone()[0]
            else:
                failures.append("catalog missing item_locations table")
            alias_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_aliases'"
            ).fetchone()
            if alias_table:
                alias_count = connection.execute(
                    "SELECT COUNT(*) FROM item_aliases"
                ).fetchone()[0]
            else:
                failures.append("catalog missing item_aliases table")
            counts = dict(
                connection.execute("SELECT kind, COUNT(*) FROM items GROUP BY kind")
            )
            curated_counts = dict(
                connection.execute(
                    """
                    SELECT source_id, COUNT(*) FROM items
                    WHERE kind = 'image' AND source_id IN (
                        'official', 'manga-curated', 'tv-curated', 'selected-output'
                    )
                    GROUP BY source_id
                    """
                )
            )
            connection.close()
            if integrity != "ok":
                failures.append(f"catalog integrity: {integrity}")
            if counts.get("image", 0) == 0:
                failures.append("catalog contains no image items")
            if counts.get("pdf", 0) != 0 or counts.get("pdf_page", 0) != 0:
                failures.append("catalog must not contain removed manga PDF sources")
            for source_id in (
                "official",
                "manga-curated",
                "tv-curated",
                "selected-output",
            ):
                if curated_counts.get(source_id, 0) == 0:
                    failures.append(f"catalog contains no images from {source_id}")
            if location_count < counts.get("image", 0):
                failures.append("catalog has fewer image locations than image assets")
            if alias_count < location_count:
                failures.append("catalog has fewer legacy aliases than image locations")
        except sqlite3.Error as exc:
            failures.append(f"catalog error: {exc}")

    result = {
        "ok": not failures,
        "skill": str(SKILL_DIR),
        "workflow_root": str(root),
        "catalog_counts": counts,
        "curated_image_counts": curated_counts,
        "image_location_count": location_count,
        "legacy_alias_count": alias_count,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
