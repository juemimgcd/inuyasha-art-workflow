#!/usr/bin/env python3

from __future__ import annotations

import io
import json
import sqlite3
import sys
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from annotate_reference import parse_identity_facet
from plan_art_task import infer_prop_forms
from prepare_reference_set import (
    manifest_identity_coverage_item,
    parse_crop_facet,
)
from search_reference_index import main as search_reference_index_main
from workflow_common import (
    cropped_identity_item,
    identity_facet_tag,
    item_identity_facets,
    load_config,
    official_facet_coverage,
    required_official_facets,
    retrieval_traits_for,
)
from validate_art_task import official_facet_coverage_failures
from validate_workflow import annotation_reference_failures
from validate_workflow import main as validate_workflow_main
from validate_workflow import source_override_failures


def item(
    item_id: str,
    subject_forms: dict[str, list[str]],
    *,
    shots: list[str] | None = None,
    tags: list[str] | None = None,
    path: str = "sheet.jpg",
) -> dict:
    return {
        "item_id": item_id,
        "relative_path": path,
        "subject_forms": subject_forms,
        "shot_types": shots or [],
        "tags": tags or [],
        "eligible_roles": ["identity"],
    }


class OfficialFacetCoverageTests(unittest.TestCase):
    def test_identity_facet_annotation_syntax_is_controlled(self) -> None:
        self.assertEqual(
            parse_identity_facet("犬夜叉=human-form:face"),
            ("犬夜叉", "human-form", "face"),
        )

    def test_negated_prop_does_not_enter_retrieval_or_prop_forms(self) -> None:
        request = "弥勒发动右掌风穴；不得出现锡杖、锡杖头或其他武器"
        self.assertNotIn("content-object:staff", retrieval_traits_for(request))
        self.assertEqual(infer_prop_forms(request), [])
        self.assertNotIn(
            "action:draw-weapon",
            retrieval_traits_for("犬夜叉右手轻扶刀柄但不拔刀"),
        )
        self.assertIn(
            "content-object:tessaiga",
            retrieval_traits_for("不要天生牙而是保留铁碎牙"),
        )
        for request in ("严禁出现锡杖", "不允许出现锡杖", "避免出现锡杖", "不希望出现锡杖"):
            with self.subTest(request=request):
                self.assertNotIn("content-object:staff", retrieval_traits_for(request))

    def test_negated_prop_possession_verbs_do_not_create_prop_evidence(self) -> None:
        cases = (
            ("没有手持锡杖", "content-object:staff", "锡杖"),
            ("不手持锡杖", "content-object:staff", "锡杖"),
            ("不带锡杖", "content-object:staff", "锡杖"),
            ("未携带锡杖", "content-object:staff", "锡杖"),
            ("弥勒空手，不持锡杖", "content-object:staff", "锡杖"),
            ("没有佩戴言灵念珠", "content-object:beads-of-subjugation", "言灵念珠"),
            ("不拿铁碎牙", "content-object:tessaiga", "铁碎牙"),
        )
        for request, trait, prop in cases:
            with self.subTest(request=request):
                self.assertNotIn(trait, retrieval_traits_for(request))
                self.assertNotIn(prop, dict(infer_prop_forms(request)))

    def test_scoped_tags_and_unambiguous_auto_facets(self) -> None:
        row = item(
            "official:file:a",
            {"犬夜叉": ["human-form"], "铁碎牙": ["untransformed-form"]},
            shots=["face", "full-body", "detail"],
            tags=["occlusion:garment-prop", "prop-attachment:waist"],
        )
        self.assertEqual(
            item_identity_facets(row, "犬夜叉", "human-form"),
            {
                "face",
                "hair-ear",
                "costume",
                "garment-overlap",
                "hands",
                "feet",
                "prop-attachment",
            },
        )
        self.assertEqual(
            item_identity_facets(row, "铁碎牙", "untransformed-form"),
            {"prop-attachment"},
        )

    def test_page_global_facets_do_not_leak_across_multiple_characters(self) -> None:
        row = item(
            "official:file:group",
            {"犬夜叉": ["half-demon-form"], "杀生丸": ["default-form"]},
            shots=["face", "full-body"],
            tags=[identity_facet_tag("犬夜叉", "half-demon-form", "face")],
        )
        self.assertEqual(
            item_identity_facets(row, "犬夜叉", "half-demon-form"), {"face"}
        )
        self.assertEqual(item_identity_facets(row, "杀生丸", "default-form"), set())

    def test_complete_set_distinguishes_hit_insufficient_and_miss(self) -> None:
        rows = [
            item(
                "official:file:face",
                {"犬夜叉": ["human-form"]},
                tags=[identity_facet_tag("犬夜叉", "human-form", "face")],
            ),
            item(
                "official:file:feet",
                {"犬夜叉": ["human-form"]},
                tags=[identity_facet_tag("犬夜叉", "human-form", "feet")],
            ),
        ]
        self.assertEqual(
            official_facet_coverage(
                rows, "犬夜叉", "human-form", ["face", "feet"]
            )["status"],
            "HIT",
        )
        self.assertEqual(
            official_facet_coverage(
                rows[:1], "犬夜叉", "human-form", ["face", "feet"]
            )["status"],
            "INSUFFICIENT",
        )
        self.assertEqual(
            official_facet_coverage(
                rows, "犬夜叉", "child-form", ["face"]
            )["status"],
            "MISS",
        )

    def test_requirements_are_shot_and_prop_aware(self) -> None:
        rows = required_official_facets(
            {"犬夜叉": "human-form"},
            {"铁碎牙": "untransformed-form"},
            "full-body",
        )
        self.assertEqual(
            rows[0]["required"], ["face", "hair-ear", "costume", "hands", "feet"]
        )
        self.assertEqual(
            rows[1]["required"], ["construction", "prop-attachment"]
        )

    def test_unspecified_shot_and_unowned_prop_do_not_invent_visible_facets(self) -> None:
        rows = required_official_facets(
            {"犬夜叉": "half-demon-form", "戈薇": "default-form"},
            {"铁碎牙": "untransformed-form"},
            None,
        )
        for requirement in rows[:2]:
            self.assertNotIn("hands", requirement["required"])
            self.assertNotIn("feet", requirement["required"])
            self.assertNotIn("garment-overlap", requirement["required"])

    def test_validator_requires_selected_union_when_catalog_is_complete(self) -> None:
        face = item(
            "official:file:face",
            {"犬夜叉": ["human-form"]},
            tags=[identity_facet_tag("犬夜叉", "human-form", "face")],
        )
        feet = item(
            "official:file:feet",
            {"犬夜叉": ["human-form"]},
            tags=[identity_facet_tag("犬夜叉", "human-form", "feet")],
        )
        failures, _warnings, _reports = official_facet_coverage_failures(
            [
                {
                    "subject": "犬夜叉",
                    "form": "human-form",
                    "required": ["face", "feet"],
                }
            ],
            [face, feet],
            [face],
            "## Layer 1: official identity\n- Result: HIT\n## Layer 2:",
        )
        self.assertTrue(
            any("miss catalog-available facets" in failure for failure in failures)
        )

    def test_validator_requires_available_facets_when_catalog_is_insufficient(self) -> None:
        face = item(
            "official:file:face",
            {"犬夜叉": ["human-form"]},
            tags=[identity_facet_tag("犬夜叉", "human-form", "face")],
        )
        failures, warnings, _reports = official_facet_coverage_failures(
            [{"subject": "犬夜叉", "form": "human-form", "required": ["face", "feet"]}],
            [face],
            [],
            "## Layer 1: official identity\n- Result: INSUFFICIENT\n## Layer 2:",
        )
        self.assertTrue(any("face" in failure for failure in failures))
        self.assertTrue(any("INSUFFICIENT" in warning for warning in warnings))

    def test_crop_facets_are_explicit_and_source_bounded(self) -> None:
        source = item(
            "official:file:full",
            {"犬夜叉": ["human-form"]},
            shots=["face", "full-body"],
        )
        face_tag = identity_facet_tag("犬夜叉", "human-form", "face")
        cropped = cropped_identity_item(source, [face_tag])
        self.assertEqual(item_identity_facets(cropped, "犬夜叉", "human-form"), {"face"})
        self.assertEqual(
            parse_crop_facet("official:file:full=犬夜叉:human-form:face"),
            ("official:file:full", face_tag),
        )
        with self.assertRaisesRegex(ValueError, "not provided"):
            cropped_identity_item(
                source,
                [identity_facet_tag("铁碎牙", "transformed-form", "construction")],
            )

    def test_legacy_crop_is_readable_but_not_a_facet_provider(self) -> None:
        source = item(
            "official:file:legacy-crop",
            {"犬夜叉": ["human-form"]},
            shots=["face", "full-body"],
        )
        legacy = manifest_identity_coverage_item(source, [0, 0, 64, 64], [])
        self.assertIsNone(legacy)
        self.assertEqual(
            official_facet_coverage(
                [row for row in [legacy] if row],
                "犬夜叉",
                "human-form",
                ["face"],
            )["status"],
            "MISS",
        )
        with self.assertRaisesRegex(ValueError, "requires identity_facets"):
            cropped_identity_item(source, [])
        with self.assertRaisesRegex(ValueError, "requires identity_facets"):
            manifest_identity_coverage_item(
                source, [0, 0, 64, 64], [], require_facets=True
            )
        face_tag = identity_facet_tag("犬夜叉", "human-form", "face")
        scoped = manifest_identity_coverage_item(
            source, [0, 0, 64, 64], [face_tag]
        )
        self.assertEqual(
            item_identity_facets(scoped, "犬夜叉", "human-form"), {"face"}
        )
        self.assertIs(manifest_identity_coverage_item(source, None, []), source)

    def test_coverage_cli_rejects_empty_facets(self) -> None:
        arguments = [
            "search_reference_index.py",
            "--source",
            "official",
            "--role",
            "identity",
            "--subject-form",
            "犬夜叉=human-form",
            "--coverage",
        ]
        with patch("sys.argv", arguments), self.assertRaisesRegex(
            SystemExit, "at least one --required-facet"
        ):
            search_reference_index_main()

    def test_coverage_cli_rejects_hard_filters(self) -> None:
        arguments = [
            "search_reference_index.py",
            "--source",
            "official",
            "--role",
            "identity",
            "--subject-form",
            "犬夜叉=human-form",
            "--coverage",
            "--required-facet",
            "face",
            "--query",
            "definitely-no-such-token",
        ]
        with patch("sys.argv", arguments), self.assertRaisesRegex(
            SystemExit, "rejects hard filters"
        ):
            search_reference_index_main()

    def test_coverage_limit_one_keeps_request_specific_series_member(self) -> None:
        arguments = [
            "search_reference_index.py",
            "--source",
            "official",
            "--role",
            "identity",
            "--subject-form",
            "犬夜叉=half-demon-form",
            "--coverage",
            "--required-facet",
            "face",
            "--required-facet",
            "hair-ear",
            "--intent-text",
            "眼部修正",
            "--collapse-candidate-series",
            "--limit",
            "1",
            "--json",
        ]
        stdout = io.StringIO()
        with (
            patch("sys.argv", arguments),
            patch(
                "search_reference_index.freshness",
                return_value=(True, "test catalog"),
            ),
            redirect_stdout(stdout),
        ):
            self.assertEqual(search_reference_index_main(), 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["coverage"]["status"], "HIT")
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(
            payload["results"][0]["relative_path"],
            "犬夜叉设定集/犬夜叉半妖形态头部表情图03.jpg",
        )
        self.assertEqual(
            payload["coverage"]["coverage_item_ids"],
            [payload["results"][0]["item_id"]],
        )

    def test_source_role_override_must_be_safe_narrow_and_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "reference.png").write_bytes(b"test")
            connection = sqlite3.connect(":memory:")
            connection.executescript(
                """
                CREATE TABLE items (item_id TEXT, eligible_roles TEXT, tags TEXT);
                CREATE TABLE item_locations (
                    item_id TEXT, source_id TEXT, relative_path TEXT,
                    subjects TEXT, forms TEXT, subject_forms TEXT, shot_types TEXT
                );
                INSERT INTO items VALUES ('item', '["content"]', '[]');
                INSERT INTO item_locations VALUES (
                    'item', 'manga-curated', 'reference.png', '[]', '[]', '{}', '[]'
                );
                """
            )
            source = {
                "id": "manga-curated",
                "path": str(root),
                "evidence_roles": ["rendering", "content"],
                "path_evidence_role_overrides": {"reference.png": ["content"]},
            }
            self.assertEqual(source_override_failures(source, connection), [])
            source["path_evidence_role_overrides"]["reference.png"] = ["identity"]
            self.assertTrue(
                any(
                    "widens source authority" in failure
                    for failure in source_override_failures(source, connection)
                )
            )
            source["path_evidence_role_overrides"] = {"missing.png": ["content"]}
            self.assertTrue(
                any(
                    "missing or unsafe" in failure
                    for failure in source_override_failures(source, connection)
                )
            )
            connection.close()

    def test_malformed_override_maps_are_reported_without_crashing(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.executescript(
            """
            CREATE TABLE items (item_id TEXT, eligible_roles TEXT, tags TEXT);
            CREATE TABLE item_locations (
                item_id TEXT, source_id TEXT, relative_path TEXT,
                subjects TEXT, forms TEXT, subject_forms TEXT, shot_types TEXT
            );
            """
        )
        for field in (
            "path_subject_form_overrides",
            "path_shot_overrides",
            "path_tag_suppressions",
            "path_evidence_role_overrides",
        ):
            with self.subTest(field=field):
                failures = source_override_failures(
                    {
                        "id": "test-source",
                        "path": "/tmp",
                        "evidence_roles": [],
                        field: [],
                    },
                    connection,
                )
                self.assertIn(
                    f"test-source {field} must be an object",
                    failures,
                )
        connection.close()

    def test_validate_workflow_main_reports_malformed_override_maps(self) -> None:
        base_config = load_config()
        official = next(
            source for source in base_config["sources"] if source["id"] == "official"
        )
        subject_path = next(iter(official["path_subject_form_overrides"]))
        shot_path = next(iter(official["path_shot_overrides"]))
        suppression_path = next(iter(official["path_tag_suppressions"]))
        malformed_cases = {
            "top-level": {
                field: []
                for field in (
                    "path_subject_form_overrides",
                    "path_shot_overrides",
                    "path_tag_suppressions",
                    "path_evidence_role_overrides",
                )
            },
            "nested": {
                "path_subject_form_overrides": {subject_path: []},
                "path_shot_overrides": {shot_path: {}},
                "path_tag_suppressions": {suppression_path: {}},
                "path_evidence_role_overrides": {subject_path: {}},
            },
        }
        workflow_root = SCRIPTS.parents[2] / "workflow/reference-workflow"
        for label, malformed in malformed_cases.items():
            with self.subTest(label=label):
                config = deepcopy(base_config)
                current_official = next(
                    source
                    for source in config["sources"]
                    if source["id"] == "official"
                )
                current_official.update(malformed)
                stdout = io.StringIO()
                with (
                    patch("validate_workflow.load_config", return_value=config),
                    patch.object(
                        sys,
                        "argv",
                        [
                            "validate_workflow.py",
                            "--workflow-root",
                            str(workflow_root),
                        ],
                    ),
                    redirect_stdout(stdout),
                ):
                    self.assertEqual(validate_workflow_main(), 2)
                payload = json.loads(stdout.getvalue())
                self.assertFalse(payload["ok"])
                self.assertTrue(
                    any("override" in failure for failure in payload["failures"])
                )

    def test_source_library_duplicate_keys_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "source-library.json"
            config.write_text(
                '{"schema_version":1,"sources":[],"sources":[]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key.*sources"):
                load_config(config)

    def test_annotations_must_resolve_to_an_item_or_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            annotations = Path(directory) / "annotations.jsonl"
            annotations.write_text(
                '{"item_id":"current"}\n'
                '{"item_id":"legacy"}\n'
                '{"item_id":"missing"}\n',
                encoding="utf-8",
            )
            connection = sqlite3.connect(":memory:")
            connection.executescript(
                """
                CREATE TABLE items (item_id TEXT PRIMARY KEY);
                CREATE TABLE item_aliases (alias_id TEXT PRIMARY KEY, item_id TEXT);
                INSERT INTO items VALUES ('current');
                INSERT INTO item_aliases VALUES ('legacy', 'current');
                """
            )
            self.assertEqual(
                annotation_reference_failures(connection, annotations),
                ["annotation item does not resolve: missing"],
            )
            connection.close()

    def test_validator_requires_honest_insufficient_evidence(self) -> None:
        face = item(
            "official:file:face",
            {"犬夜叉": ["human-form"]},
            tags=[identity_facet_tag("犬夜叉", "human-form", "face")],
        )
        failures, _warnings, _reports = official_facet_coverage_failures(
            [
                {
                    "subject": "犬夜叉",
                    "form": "human-form",
                    "required": ["face", "feet"],
                }
            ],
            [face],
            [face],
            "## Layer 1: official identity\n- Result: HIT\n## Layer 2:",
        )
        self.assertTrue(
            any("expected INSUFFICIENT" in failure for failure in failures)
        )

if __name__ == "__main__":
    unittest.main()
