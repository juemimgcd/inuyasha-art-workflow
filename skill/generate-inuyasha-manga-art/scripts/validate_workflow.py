#!/usr/bin/env python3
"""Validate the skill, growing curated libraries, catalog, and helper runtime."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from build_reference_index import freshness
from visual_ab_eval import effective_results
from visual_ab_eval import load_dataset as load_visual_eval_dataset
from workflow_common import (
    CONFIG_PATH,
    FORM_VALUES,
    SKILL_DIR,
    VIEW_ANGLE_VALUES,
    library_signature,
    load_config,
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
    "references/retrieval-benchmark.json",
    "references/visual-eval-v2.json",
    "references/visual-edit-eval-v1.json",
    "references/visual-manga-style-eval-v1.json",
    "references/visual-manga-style-edit-eval-v1.json",
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
    "scripts/benchmark_reference_retrieval.py",
    "scripts/visual_ab_eval.py",
    "scripts/image_sheet.py",
    "scripts/preference_profile.py",
    "scripts/validate_all_tasks.py",
    "scripts/migrate_art_tasks.py",
    "scripts/archive_art_task.py",
    "scripts/run-python",
    "scripts/run-python.ps1",
)
EXPECTED_CATALOG_SCHEMA = "8"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow-root",
        type=Path,
        help=(
            "Validate a specific packaged workflow-data root instead of the "
            "configured live root."
        ),
    )
    parser.add_argument("--visual-run-dir", type=Path)
    parser.add_argument(
        "--require-visual-promotion",
        action="store_true",
        help=(
            "Fail unless --visual-run-dir has a complete feedback-aware "
            "promote_candidate verdict."
        ),
    )
    return parser.parse_args()


def _string_list_failures(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        return [f"{label} must be a list of non-empty strings"]
    return []


def identity_ledger_failures(ledger: dict) -> list[str]:
    """Validate legacy feature lists and structured positive prop topology."""
    failures = []
    if ledger.get("schema_version") != 1:
        failures.append("identity-ledgers.json must use schema 1")
    characters = ledger.get("characters")
    if not isinstance(characters, dict) or "犬夜叉" not in characters:
        failures.append("identity-ledgers.json must include 犬夜叉")
        return failures
    for subject, profile in characters.items():
        label = f"identity ledger {subject}"
        if not isinstance(profile, dict):
            failures.append(f"{label} must be an object")
            continue
        for field in ("common", "exclusions"):
            failures.extend(
                _string_list_failures(profile.get(field, []), f"{label}.{field}")
            )
        forms = profile.get("forms")
        if not isinstance(forms, dict) or not forms:
            failures.append(f"{label}.forms must be a non-empty object")
            continue
        for form, record in forms.items():
            form_label = f"{label}.forms.{form}"
            if isinstance(record, list):
                failures.extend(_string_list_failures(record, form_label))
                continue
            if not isinstance(record, dict):
                failures.append(f"{form_label} must be a feature list or object")
                continue
            failures.extend(
                _string_list_failures(record.get("features"), f"{form_label}.features")
            )
            topology = record.get("topology")
            if not isinstance(topology, dict):
                failures.append(f"{form_label}.topology must be an object")
                continue
            failures.extend(
                _string_list_failures(
                    topology.get("connected_sequence"),
                    f"{form_label}.topology.connected_sequence",
                )
            )
            counts = topology.get("counts")
            if not isinstance(counts, dict) or not counts:
                failures.append(f"{form_label}.topology.counts must be non-empty")
            elif not all(
                isinstance(name, str)
                and name.strip()
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count > 0
                for name, count in counts.items()
            ):
                failures.append(
                    f"{form_label}.topology.counts must map names to positive integers"
                )
        inference = profile.get("form_inference", {})
        if not isinstance(inference, dict):
            failures.append(f"{label}.form_inference must be an object")
            continue
        for form, rules in inference.items():
            rule_label = f"{label}.form_inference.{form}"
            if form not in forms:
                failures.append(f"{rule_label} references an unknown form")
                continue
            if isinstance(rules, list):
                failures.extend(_string_list_failures(rules, rule_label))
                if not rules:
                    failures.append(f"{rule_label} must declare at least one alias")
                continue
            if not isinstance(rules, dict) or set(rules) - {"explicit", "context"}:
                failures.append(
                    f"{rule_label} must use only explicit/context alias groups"
                )
                continue
            for strength in ("explicit", "context"):
                failures.extend(
                    _string_list_failures(
                        rules.get(strength, []), f"{rule_label}.{strength}"
                    )
                )
            if not any(rules.get(strength) for strength in ("explicit", "context")):
                failures.append(f"{rule_label} must declare at least one alias")
        view_traits = profile.get("view_traits", {})
        if not isinstance(view_traits, dict):
            failures.append(f"{label}.view_traits must be an object")
        else:
            for form, views in view_traits.items():
                view_label = f"{label}.view_traits.{form}"
                if form not in forms:
                    failures.append(f"{view_label} references an unknown form")
                    continue
                if not isinstance(views, dict) or not views:
                    failures.append(f"{view_label} must be a non-empty object")
                    continue
                for view_angle, traits in views.items():
                    trait_label = f"{view_label}.{view_angle}"
                    if view_angle not in VIEW_ANGLE_VALUES:
                        failures.append(
                            f"{trait_label} references an unknown view angle"
                        )
                    failures.extend(_string_list_failures(traits, trait_label))
                    if isinstance(traits, list) and not traits:
                        failures.append(
                            f"{trait_label} must declare at least one trait"
                        )
        rendering_fallbacks = profile.get("rendering_fallbacks", {})
        if not isinstance(rendering_fallbacks, dict):
            failures.append(f"{label}.rendering_fallbacks must be an object")
        else:
            for view_angle, mapping in rendering_fallbacks.items():
                fallback_label = f"{label}.rendering_fallbacks.{view_angle}"
                if view_angle not in VIEW_ANGLE_VALUES:
                    failures.append(
                        f"{fallback_label} references an unknown view angle"
                    )
                if not isinstance(mapping, dict) or not mapping:
                    failures.append(f"{fallback_label} must be a non-empty object")
                    continue
                for fallback_subject, fallback_form in mapping.items():
                    if fallback_subject not in characters:
                        failures.append(
                            f"{fallback_label} references unknown subject "
                            f"{fallback_subject}"
                        )
                    if fallback_form not in FORM_VALUES:
                        failures.append(
                            f"{fallback_label}.{fallback_subject} references "
                            f"unknown form {fallback_form}"
                        )
    return failures


def main() -> int:
    args = parse_args()
    failures = []
    warnings = []
    if args.require_visual_promotion and args.visual_run_dir is None:
        failures.append(
            "--require-visual-promotion requires --visual-run-dir"
        )
    for relative in REQUIRED_FILES:
        path = SKILL_DIR / relative
        if not path.is_file():
            failures.append(f"missing required file: {path}")

    config = load_config(CONFIG_PATH)
    identity_ledgers = json.loads(
        (SKILL_DIR / "references/identity-ledgers.json").read_text(encoding="utf-8")
    )
    failures.extend(identity_ledger_failures(identity_ledgers))
    benchmark_path = SKILL_DIR / "references/retrieval-benchmark.json"
    benchmark = {}
    benchmark_case_count = 0
    try:
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
        if benchmark.get("schema_version") != 1:
            failures.append("retrieval-benchmark.json must use schema 1")
        cases = benchmark.get("cases", [])
        if not isinstance(cases, list):
            failures.append("retrieval benchmark cases must be a list")
            cases = []
        benchmark_case_count = len(cases)
        case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
        if not cases or len(case_ids) != len(set(case_ids)):
            failures.append("retrieval benchmark cases must be non-empty and unique")
        for name, threshold in benchmark.get("thresholds", {}).items():
            if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
                failures.append(f"invalid retrieval benchmark threshold: {name}")
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"invalid retrieval benchmark dataset: {exc}")
    visual_eval_case_count = 0
    visual_edit_eval_case_count = 0
    visual_manga_style_eval_case_count = 0
    visual_manga_style_edit_eval_case_count = 0
    visual_promotion = {
        "checked": False,
        "promotion_passed": None,
        "verdict": "not-checked",
    }
    try:
        visual_eval = load_visual_eval_dataset(
            SKILL_DIR / "references/visual-eval-v2.json"
        )
        visual_eval_case_count = len(visual_eval["cases"])
        visual_edit_eval = load_visual_eval_dataset(
            SKILL_DIR / "references/visual-edit-eval-v1.json"
        )
        visual_edit_eval_case_count = len(visual_edit_eval["cases"])
        visual_manga_style_eval = load_visual_eval_dataset(
            SKILL_DIR / "references/visual-manga-style-eval-v1.json"
        )
        visual_manga_style_eval_case_count = len(
            visual_manga_style_eval["cases"]
        )
        visual_manga_style_edit_eval = load_visual_eval_dataset(
            SKILL_DIR / "references/visual-manga-style-edit-eval-v1.json"
        )
        visual_manga_style_edit_eval_case_count = len(
            visual_manga_style_edit_eval["cases"]
        )
    except (OSError, TypeError, ValueError) as exc:
        failures.append(f"invalid visual evaluation dataset: {exc}")
    if args.visual_run_dir is not None:
        try:
            effective = effective_results(args.visual_run_dir.expanduser().resolve())
            visual_promotion = {
                "checked": True,
                "run_dir": str(args.visual_run_dir.expanduser().resolve()),
                "promotion_passed": bool(effective.get("promotion_passed")),
                "verdict": effective.get("verdict"),
                "candidate_critical_failures": effective.get(
                    "critical_failures", {}
                ).get("candidate", []),
            }
            if (
                args.require_visual_promotion
                and not visual_promotion["promotion_passed"]
            ):
                failures.append(
                    "visual workflow revision is not promotable: "
                    f"{visual_promotion['verdict']}"
                )
        except (OSError, TypeError, ValueError) as exc:
            visual_promotion = {
                "checked": True,
                "promotion_passed": False,
                "verdict": "incomplete-or-invalid",
                "error": str(exc),
            }
            if args.require_visual_promotion:
                failures.append(f"visual promotion gate failed: {exc}")
            else:
                warnings.append(f"visual promotion could not be read: {exc}")
    else:
        warnings.append(
            "structural validation only; ok=true does not prove generated-image quality"
        )
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
        if source["id"] in {"manga-curated", "tv-curated"} and not {
            "rendering",
            "content",
        }.issubset(roles):
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

    root = workflow_root(config, args.workflow_root)
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
                "authority",
                "folder_path",
                "content_label",
                "folder_tags",
                "subjects",
                "forms",
                "subject_forms",
                "shot_types",
                "filename_terms",
                "duplicate_count",
                "eligible_roles",
            }
            missing_columns = required_columns - item_columns
            if missing_columns:
                failures.append(
                    f"catalog missing folder-aware columns: {sorted(missing_columns)}"
                )
            else:
                form_rows = {
                    row[0]: (
                        json.loads(row[1]),
                        json.loads(row[2]),
                    )
                    for row in connection.execute(
                        "SELECT relative_path, forms, subject_forms FROM items "
                        "WHERE source_id = 'official' AND relative_path IN (?, ?, ?, ?, ?)",
                        (
                            "犬夜叉设定集/犬夜叉人类形态图01.jpg",
                            "犬夜叉设定集/犬夜叉全身图带铁碎牙01.jpg",
                            "珊瑚设定集/珊瑚战斗服与飞来骨图01.jpg",
                            "珊瑚设定集/珊瑚退治屋服全身图02.jpg",
                            "铁碎牙设定集/铁碎牙变化前后形态图01.jpg",
                        ),
                    )
                }
                human_sheet = form_rows.get(
                    "犬夜叉设定集/犬夜叉人类形态图01.jpg", ([], {})
                )
                if human_sheet[1].get("犬夜叉") != ["human-form"]:
                    failures.append("official human-form sheet is not indexed exactly")
                tessaiga_sheet = form_rows.get(
                    "犬夜叉设定集/犬夜叉全身图带铁碎牙01.jpg", ([], {})
                )
                if tessaiga_sheet[1].get("犬夜叉") != ["half-demon-form"]:
                    failures.append(
                        "Tessaiga full-body sheet must keep Inuyasha half-demon-form"
                    )
                if tessaiga_sheet[1].get("铁碎牙") != ["untransformed-form"]:
                    failures.append(
                        "Inuyasha full-body sheet must keep Tessaiga untransformed-form"
                    )
                sango_battle = form_rows.get(
                    "珊瑚设定集/珊瑚战斗服与飞来骨图01.jpg", ([], {})
                )
                if sango_battle[1].get("珊瑚") != ["battle-armor-form"]:
                    failures.append("Sango battle sheet is not indexed exactly")
                sango_demon_slayer = form_rows.get(
                    "珊瑚设定集/珊瑚退治屋服全身图02.jpg", ([], {})
                )
                if sango_demon_slayer[1].get("珊瑚") != ["demon-slayer-form"]:
                    failures.append("Sango demon-slayer sheet is not indexed exactly")
                tessaiga_forms = form_rows.get(
                    "铁碎牙设定集/铁碎牙变化前后形态图01.jpg", ([], {})
                )
                if tessaiga_forms[1].get("铁碎牙") != [
                    "transformed-form",
                    "untransformed-form",
                ]:
                    failures.append(
                        "Tessaiga setting sheet must expose exactly both prop forms"
                    )
                child_authority = connection.execute(
                    "SELECT authority FROM items WHERE source_id = 'official' "
                    "AND relative_path = ?",
                    ("犬夜叉设定集/犬夜叉幼年形态全身图01.png",),
                ).fetchone()
                if (
                    not child_authority
                    or child_authority[0] != "user-directed-derived-identity"
                ):
                    failures.append(
                        "user-directed child-form derivative has wrong item authority"
                    )
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
                excluded_official_outputs = connection.execute(
                    "SELECT COUNT(*) FROM items WHERE source_id = 'official' "
                    "AND relative_path LIKE 'output/%'"
                ).fetchone()[0]
                if excluded_official_outputs:
                    failures.append("official output directory leaked into catalog")
                authority_conflicts = connection.execute(
                    """
                    SELECT item_id FROM items
                    WHERE EXISTS (
                        SELECT 1 FROM json_each(tags)
                        WHERE value = 'reference-role:content-only'
                    ) AND EXISTS (
                        SELECT 1 FROM json_each(eligible_roles)
                        WHERE value = 'identity'
                    )
                    """
                ).fetchall()
                if authority_conflicts:
                    failures.append(
                        "content-only references remain eligible for identity: "
                        + ", ".join(row[0] for row in authority_conflicts)
                    )
                benchmark_item_ids = {
                    item_id
                    for case in benchmark.get("cases", [])
                    if isinstance(case, dict)
                    for item_id in case.get("relevant_item_ids", [])
                }
                if benchmark_item_ids:
                    placeholders = ", ".join("?" for _ in benchmark_item_ids)
                    known_benchmark_ids = {
                        row[0]
                        for row in connection.execute(
                            f"SELECT item_id FROM items WHERE item_id IN ({placeholders})",
                            sorted(benchmark_item_ids),
                        )
                    }
                    missing_benchmark_ids = benchmark_item_ids - known_benchmark_ids
                    if missing_benchmark_ids:
                        failures.append(
                            "retrieval benchmark references unknown items: "
                            + ", ".join(sorted(missing_benchmark_ids))
                        )
                metadata_rows = connection.execute(
                    "SELECT item_id, subjects, forms, subject_forms, shot_types, tags "
                    "FROM items WHERE kind = 'image'"
                ).fetchall()
                for (
                    item_id,
                    subjects_json,
                    forms_json,
                    subject_forms_json,
                    shots_json,
                    tags_json,
                ) in metadata_rows:
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
                    if {
                        "view-angle:back",
                        "suitable-for:back-view",
                    } & tags and "back-view" not in shots:
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
        "retrieval_benchmark_cases": benchmark_case_count,
        "visual_eval_cases": visual_eval_case_count,
        "visual_edit_eval_cases": visual_edit_eval_case_count,
        "visual_manga_style_eval_cases": visual_manga_style_eval_case_count,
        "visual_manga_style_edit_eval_cases": visual_manga_style_edit_eval_case_count,
        "validation_scope": (
            "structural-and-visual-promotion"
            if args.require_visual_promotion
            else (
                "structural-with-visual-diagnostic"
                if args.visual_run_dir is not None
                else "structural-only"
            )
        ),
        "visual_promotion": visual_promotion,
        "failures": failures,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
