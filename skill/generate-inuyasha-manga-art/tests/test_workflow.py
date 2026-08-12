from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from argparse import ArgumentTypeError
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from annotate_reference import parse_trait
from benchmark_reference_retrieval import first_relevant_rank, metric_summary
from composite_local_microfix import composite_local_edit, outside_edit_box_equal
from continue_art_task import (
    context_box_for,
    inherited_reference_arguments,
    recorded_attempt_source,
)
from init_art_task import qa_items
from prepare_reference_set import (
    file_hash,
    image_pixel_hash,
    instruction_for,
    parse_box,
    parse_crop,
    render_external_transport,
    render_item,
    source_crop_pixel_hash,
    validate_crop_box,
    validate_reference,
    validate_reference_order,
)
from record_attempt import main as record_attempt_main
from reference_feedback_report import duration_summary
from task_workflow import (
    CHANGE_CATEGORIES,
    compile_prompt,
    elapsed_seconds,
    feedback_rank,
    latency_budget,
    prompt_limit,
    reference_performance,
)
from validate_art_task import (
    candidate_source_failures,
    consecutive_technical_errors,
    crop_derives_from_source,
    retrieval_result,
    technical_retry_limit_reached,
    unchanged_consecutive_errors,
)
from workflow_common import (
    CONFIG_PATH,
    annotation_shot_types,
    eligible_reference_roles,
    infer_retrieval_traits,
    infer_structured_metadata,
    infer_subjects,
    load_config,
    repository_root,
    resolve_recorded_path,
    retrieval_relevance,
    visible_files,
)


class PortabilityTests(unittest.TestCase):
    def test_config_resolves_bundled_sources_from_repository_root(self) -> None:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = load_config()
        root = repository_root()
        expected_workflow_root = (
            root / "workflow" / "reference-workflow"
            if raw["workflow_root"].startswith("${REPO_ROOT}/")
            else Path(raw["workflow_root"]).resolve()
        )
        self.assertEqual(Path(config["workflow_root"]), expected_workflow_root)
        for source in config["sources"]:
            self.assertTrue(Path(source["path"]).is_absolute())
            self.assertTrue(Path(source["path"]).is_dir(), source["id"])

    def test_config_keeps_repository_tokens_in_source_file(self) -> None:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not raw["workflow_root"].startswith("${REPO_ROOT}/"):
            self.skipTest("installed configuration intentionally uses absolute paths")
        self.assertEqual(
            raw["workflow_root"], "${REPO_ROOT}/workflow/reference-workflow"
        )
        self.assertTrue(
            all(source["path"].startswith("${REPO_ROOT}/") for source in raw["sources"])
        )

    def test_historical_path_alias_accepts_windows_separators(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target_root = Path(temp) / "workflow"
            expected = target_root / "tasks" / "sample" / "result.png"
            config = {
                "path_aliases": [{"from": "C:/legacy/workflow", "to": str(target_root)}]
            }
            actual = resolve_recorded_path(
                r"C:\legacy\workflow\tasks\sample\result.png", config
            )
            self.assertEqual(actual, expected.resolve())

    def test_historical_alias_wins_when_original_machine_path_still_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy_root = root / "legacy"
            portable_root = root / "portable"
            legacy_file = legacy_root / "tasks" / "sample.json"
            legacy_file.parent.mkdir(parents=True)
            legacy_file.write_text("legacy", encoding="utf-8")
            config = {
                "path_aliases": [{"from": str(legacy_root), "to": str(portable_root)}]
            }
            self.assertEqual(
                resolve_recorded_path(legacy_file, config),
                (portable_root / "tasks" / "sample.json").resolve(),
            )

    def test_workflow_home_environment_overrides_copied_skill_location(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, {"INUYASHA_WORKFLOW_HOME": temp}),
        ):
            self.assertEqual(repository_root(), Path(temp).resolve())


class MetadataTests(unittest.TestCase):
    def test_intent_traits_map_specific_high_frequency_phrases(self) -> None:
        self.assertEqual(
            infer_retrieval_traits("犬夜叉从背后拥抱戈薇"),
            ["action:embrace-from-behind", "interaction:body-contact"],
        )
        self.assertEqual(
            infer_retrieval_traits("幼年犬夜叉蹲坐抱球"),
            [
                "action:hold",
                "action:crouch",
                "interaction:hand-prop",
                "content-object:ball",
            ],
        )

    def test_intent_traits_do_not_confuse_names_or_style_with_weather(self) -> None:
        traits = infer_retrieval_traits("十六夜的黑白漫画画风人物设定")
        self.assertNotIn("background:night", traits)
        self.assertNotIn("effect-type:wind", traits)

    def test_intent_traits_cover_sleeves_weapons_and_grave_scenes(self) -> None:
        traits = infer_retrieval_traits(
            "犬夜叉把双手藏在袖中，在墓碑前挥动铁碎牙"
        )
        self.assertIn("action:sleeve-hidden-hands", traits)
        self.assertIn("action:swing-weapon", traits)
        self.assertIn("content-object:grave", traits)
        self.assertIn("content-object:tessaiga", traits)
        self.assertIn("content-object:robe-sleeve", traits)

    def test_source_exclude_globs_skip_derived_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "official").mkdir()
            (root / "output").mkdir()
            (root / "official" / "sheet.png").write_bytes(b"sheet")
            (root / "output" / "candidate.png").write_bytes(b"candidate")
            relative = {
                path.relative_to(root).as_posix()
                for path in visible_files(root, ["output/**"])
            }
            self.assertEqual(relative, {"official/sheet.png"})

    def test_item_role_tag_can_remove_identity_authority(self) -> None:
        self.assertEqual(
            eligible_reference_roles(
                ["identity"], ["reference-role:content-only"]
            ),
            [],
        )
        self.assertEqual(
            eligible_reference_roles(["rendering", "content"], []),
            ["content", "rendering"],
        )

    def test_field_aware_ranking_explains_exact_action(self) -> None:
        exact_item = {
            "tags": ["action:embrace-from-behind"],
            "filename_terms": ["人物参考"],
            "subjects": ["犬夜叉", "戈薇"],
            "subject_forms": {
                "犬夜叉": ["half-demon-form"],
                "戈薇": ["default-form"],
            },
            "shot_types": ["two-shot"],
            "folder_tags": ["犬夜叉"],
            "eligible_roles": ["content", "rendering"],
            "relative_path": "犬夜叉/reference.png",
        }
        loose_item = {**exact_item, "tags": [], "relative_path": "犬夜叉/拥抱参考.png"}
        exact_score, reasons = retrieval_relevance(
            exact_item,
            query_terms=["action:embrace-from-behind"],
            subject_forms=[("犬夜叉", "half-demon-form")],
            shots=["two-shot"],
            role="content",
        )
        loose_score, _ = retrieval_relevance(
            loose_item,
            query_terms=["embrace"],
            subject_forms=[("犬夜叉", "half-demon-form")],
            shots=["two-shot"],
            role="content",
        )
        self.assertGreater(exact_score, loose_score)
        self.assertIn("tag exact: action:embrace-from-behind", reasons)
        self.assertIn("subject-form exact: 犬夜叉=half-demon-form", reasons)

    def test_long_subject_does_not_leak_short_subject(self) -> None:
        self.assertEqual(infer_subjects("戈薇爷爷全身表情图"), {"戈薇爷爷"})

    def test_separate_subject_mentions_are_preserved(self) -> None:
        self.assertEqual(infer_subjects("戈薇-戈薇爷爷双人图"), {"戈薇", "戈薇爷爷"})

    def test_folder_default_supplies_standard_form(self) -> None:
        metadata = infer_structured_metadata(
            Path("戈薇设定集/戈薇冬装图01.jpg"),
            {"folder_form_defaults": {"戈薇设定集": ["default-form"]}},
        )
        self.assertEqual(metadata["forms"], ["default-form"])

    def test_inuyasha_default_form_can_alias_half_demon(self) -> None:
        metadata = infer_structured_metadata(
            Path("犬夜叉/犬夜叉__默认形态__上身__动作__01.png"),
            {"subject_form_aliases": {"犬夜叉": {"default-form": ["half-demon-form"]}}},
        )
        self.assertEqual(metadata["forms"], ["default-form", "half-demon-form"])

    def test_mixed_form_two_shot_pairs_forms_per_character(self) -> None:
        metadata = infer_structured_metadata(
            Path("犬夜叉/犬夜叉-戈薇__人类形态__双人__同框__01.png"),
            {"subject_form_aliases": {"犬夜叉": {"default-form": ["half-demon-form"]}}},
        )
        self.assertEqual(metadata["subject_forms"]["犬夜叉"], ["human-form"])
        self.assertEqual(metadata["subject_forms"]["戈薇"], ["default-form"])
        self.assertEqual(metadata["forms"], ["default-form", "human-form"])

    def test_explicit_form_sequence_maps_to_subject_sequence(self) -> None:
        metadata = infer_structured_metadata(
            Path("犬夜叉/桔梗-犬夜叉__默认形态-人类形态__双人全身__01.png"),
            {},
        )
        self.assertEqual(metadata["subject_forms"]["桔梗"], ["default-form"])
        self.assertEqual(metadata["subject_forms"]["犬夜叉"], ["human-form"])

    def test_inuyasha_alias_does_not_leak_to_kagome(self) -> None:
        metadata = infer_structured_metadata(
            Path("戈薇/犬夜叉-戈薇__默认形态__双人__同框__01.png"),
            {"subject_form_aliases": {"犬夜叉": {"default-form": ["half-demon-form"]}}},
        )
        self.assertIn("half-demon-form", metadata["subject_forms"]["犬夜叉"])
        self.assertNotIn("half-demon-form", metadata["subject_forms"]["戈薇"])

    def test_back_view_annotation_adds_back_view_shot(self) -> None:
        self.assertEqual(
            annotation_shot_types({"view-angle:back", "suitable-for:weapon-mount"}),
            {"back-view"},
        )

    def test_visual_trait_values_are_controlled(self) -> None:
        self.assertEqual(parse_trait("view-angle=back"), "view-angle:back")
        self.assertEqual(parse_trait("action=pass-ball"), "action:pass-ball")
        self.assertEqual(parse_trait("content-object=mirror"), "content-object:mirror")
        with self.assertRaises(ArgumentTypeError):
            parse_trait("view-angle=backwards")


class RetrievalBenchmarkTests(unittest.TestCase):
    def test_first_relevant_rank_accepts_multiple_truth_items(self) -> None:
        self.assertEqual(
            first_relevant_rank(["wrong", "right-b"], {"right-a", "right-b"}),
            2,
        )
        self.assertIsNone(first_relevant_rank(["wrong"], {"right"}))

    def test_metric_summary_reports_top_k_and_mrr(self) -> None:
        self.assertEqual(
            metric_summary([1, 2, None, 1], [1, 3]),
            {"recall_at_1": 0.5, "recall_at_3": 0.75, "mrr": 0.625},
        )


class ReferenceValidationTests(unittest.TestCase):
    def row(
        self,
        *,
        source: str,
        subjects: list[str],
        forms: list[str],
        subject_forms: dict[str, list[str]] | None = None,
        eligible_roles: list[str] | None = None,
    ) -> dict:
        default_roles = {
            "official": ["identity"],
            "manga-curated": ["rendering", "composition", "content"],
            "tv-curated": ["rendering", "composition", "content", "palette"],
            "selected-output": ["continuity"],
            "user-continuity": ["continuity", "target"],
        }
        return {
            "source_id": source,
            "subjects": json.dumps(subjects, ensure_ascii=False),
            "forms": json.dumps(forms),
            "subject_forms": json.dumps(subject_forms or {}, ensure_ascii=False),
            "eligible_roles": json.dumps(
                default_roles.get(source, [])
                if eligible_roles is None
                else eligible_roles
            ),
        }

    def test_reference_order(self) -> None:
        validate_reference_order(
            [("style", "style-1"), ("identity", "identity-1"), ("form", "form-1")]
        )
        with self.assertRaises(SystemExit):
            validate_reference_order([("identity", "identity-1"), ("style", "style-1")])

    def test_selected_medium_exact_form_reference_is_isolated(self) -> None:
        row = self.row(
            source="manga-curated",
            subjects=["犬夜叉"],
            forms=["child-form"],
            subject_forms={"犬夜叉": ["child-form"]},
        )
        validate_reference(row, "form", "manga:test", "manga", {"犬夜叉": "child-form"})
        self.assertIn("exact requested form", instruction_for("form", "manga"))
        with self.assertRaises(SystemExit):
            validate_reference(
                row, "form", "manga:test", "tv", {"犬夜叉": "child-form"}
            )

    def test_identity_form_mismatch_is_rejected(self) -> None:
        row = self.row(
            source="official", subjects=["犬夜叉"], forms=["half-demon-form"]
        )
        with self.assertRaises(SystemExit):
            validate_reference(
                row, "identity", "official:test", "manga", {"犬夜叉": "human-form"}
            )

    def test_item_level_role_blocks_content_only_identity(self) -> None:
        row = self.row(
            source="official",
            subjects=["十六夜"],
            forms=["default-form"],
            subject_forms={"十六夜": ["default-form"]},
            eligible_roles=["content"],
        )
        with self.assertRaises(SystemExit):
            validate_reference(
                row,
                "identity",
                "official:content-only",
                "manga",
                {"十六夜": "default-form"},
            )

    def test_item_with_no_eligible_roles_is_rejected(self) -> None:
        row = self.row(
            source="official",
            subjects=["十六夜"],
            forms=["default-form"],
            eligible_roles=[],
        )
        with self.assertRaises(SystemExit):
            validate_reference(
                row,
                "identity",
                "official:excluded-item",
                "manga",
                {"十六夜": "default-form"},
            )

    def test_style_source_must_match_medium(self) -> None:
        row = self.row(source="tv-curated", subjects=["犬夜叉"], forms=[])
        with self.assertRaises(SystemExit):
            validate_reference(row, "style", "tv:test", "manga", {})

    def test_tv_content_is_allowed_for_manga_without_style_authority(self) -> None:
        row = self.row(
            source="tv-curated", subjects=["犬夜叉"], forms=["half-demon-form"]
        )
        validate_reference(
            row,
            "content",
            "tv:test",
            "manga",
            {"犬夜叉": "half-demon-form"},
        )
        with self.assertRaises(SystemExit):
            validate_reference(row, "style", "tv:test", "manga", {})

    def test_content_rejects_non_curated_sources(self) -> None:
        row = self.row(source="selected-output", subjects=[], forms=[])
        with self.assertRaises(SystemExit):
            validate_reference(row, "content", "selected:test", "manga", {})

    def test_content_requires_one_exact_focus_reference(self) -> None:
        with self.assertRaises(ValueError):
            instruction_for("content", "manga", source_medium="tv")
        instruction = instruction_for(
            "content",
            "manga",
            focus="只参考冥道入口的张开形态",
            source_medium="tv",
        )
        self.assertIn("cross-medium tv-to-manga", instruction)
        self.assertIn("Ignore all tv palette", instruction)
        self.assertIn("Exact focus: 只参考冥道入口的张开形态", instruction)
        derived = instruction_for(
            "content",
            "manga",
            focus="只参考动画原创妖怪的可见结构",
            source_medium="tv",
            content_provenance="fallback-medium-original",
        )
        self.assertIn("source-medium-derived adaptation", derived)
        self.assertIn("do not present it as selected-medium canonical", derived)
        with self.assertRaises(ValueError):
            instruction_for(
                "content",
                "manga",
                focus="只参考漫画内容",
                source_medium="manga",
                content_provenance="fallback-medium-original",
            )
        with self.assertRaises(SystemExit):
            validate_reference_order(
                [
                    ("style", "style-1"),
                    ("identity", "identity-1"),
                    ("content", "content-1"),
                    ("content", "content-2"),
                ]
            )

    def test_reference_validation_uses_subject_form_pair(self) -> None:
        row = self.row(
            source="official",
            subjects=["犬夜叉", "戈薇"],
            forms=["default-form", "half-demon-form"],
            subject_forms={
                "犬夜叉": ["default-form", "half-demon-form"],
                "戈薇": ["default-form"],
            },
        )
        with self.assertRaises(SystemExit):
            validate_reference(
                row, "identity", "official:test", "manga", {"戈薇": "half-demon-form"}
            )

    def test_selected_output_is_continuity_only(self) -> None:
        row = self.row(
            source="selected-output",
            subjects=["犬夜叉"],
            forms=["half-demon-form"],
        )
        validate_reference(
            row,
            "continuity",
            "selected-output:test",
            "manga",
            {"犬夜叉": "half-demon-form"},
        )
        with self.assertRaises(SystemExit):
            validate_reference(
                row,
                "style",
                "selected-output:test",
                "manga",
                {"犬夜叉": "half-demon-form"},
            )

    def test_only_one_selected_output_reference_is_allowed(self) -> None:
        with self.assertRaises(SystemExit):
            validate_reference_order(
                [
                    ("style", "style-1"),
                    ("identity", "identity-1"),
                    ("continuity", "selected-1"),
                    ("continuity", "selected-2"),
                ]
            )

    def test_target_only_is_valid_for_microfix_preparation(self) -> None:
        validate_reference_order([("target", "user-supplied:test")])

    def test_crop_parser_and_bounds(self) -> None:
        item_id, crop_box = parse_crop("official:file:test=10,20,30,40")
        self.assertEqual(item_id, "official:file:test")
        self.assertEqual(crop_box, (10, 20, 30, 40))
        validate_crop_box(crop_box, (100, 100))
        with self.assertRaises(ValueError):
            validate_crop_box(crop_box, (39, 59))

    def test_plain_box_parser(self) -> None:
        self.assertEqual(parse_box("10,20,30,40"), (10, 20, 30, 40))
        with self.assertRaises(ArgumentTypeError):
            parse_box("10,20,30")

    def test_task_local_crop_keeps_requested_dimensions(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "prepared"
            output.mkdir()
            Image.new("RGB", (100, 80), "white").save(source)
            row = {
                "kind": "image",
                "path": str(source),
                "item_id": "official:file:test",
            }
            prepared = render_item(row, "identity", output, 150, (10, 20, 30, 40))
            with Image.open(prepared) as image:
                self.assertEqual(image.size, (30, 40))
            self.assertEqual(list(output.iterdir()), [prepared])

    def test_external_transport_keeps_source_and_records_derivation(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            target = root / "transport.jpg"
            Image.new("RGBA", (1600, 1000), (0, 0, 0, 0)).save(source)
            source_before = source.read_bytes()
            transport = render_external_transport(source, target, 960, 88)
            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(transport["source_dimensions"], [1600, 1000])
            self.assertEqual(transport["rendered_dimensions"], [960, 600])
            self.assertEqual(transport["rendered_content_hash"], file_hash(target))
            with Image.open(target) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (960, 600))

    def test_crop_instruction_names_exact_focus(self) -> None:
        instruction = instruction_for(
            "identity",
            "manga",
            (80, 120, 250, 310),
            "rear waist, belt, mount, and sheath overlap.",
        )
        self.assertIn("task-local crop", instruction)
        self.assertIn("rear waist, belt, mount", instruction)

    def test_existing_crop_is_regenerated_from_source(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "prepared"
            output.mkdir()
            Image.new("RGB", (20, 20), "red").save(source)
            row = {
                "kind": "image",
                "path": str(source),
                "item_id": "official:file:test",
            }
            prepared = render_item(row, "identity", output, 150, (0, 0, 10, 10))
            Image.new("RGB", (10, 10), "blue").save(prepared)
            refreshed = render_item(row, "identity", output, 150, (0, 0, 10, 10))
            self.assertEqual(
                image_pixel_hash(refreshed),
                source_crop_pixel_hash(source, (0, 0, 10, 10)),
            )

    def test_crop_derivation_rejects_substituted_pixels(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            rendered = root / "rendered.png"
            Image.new("RGB", (20, 20), "red").save(source)
            Image.new("RGB", (10, 10), "blue").save(rendered)
            self.assertFalse(crop_derives_from_source(source, rendered, (0, 0, 10, 10)))

    def test_inherited_crop_arguments_preserve_coordinates_and_focus(self) -> None:
        arguments = inherited_reference_arguments(
            {
                "role": "identity",
                "item_id": "official:file:test",
                "crop_box": [1, 2, 30, 40],
                "focus": "rear waist and sheath mount",
            }
        )
        self.assertIn("official:file:test=1,2,30,40", arguments)
        self.assertIn("official:file:test=rear waist and sheath mount", arguments)

    def test_context_box_is_clipped_to_image(self) -> None:
        self.assertEqual(
            context_box_for((5, 10, 20, 30), (100, 80), 16),
            (0, 0, 41, 56),
        )

    def test_recorded_candidate_can_be_resolved_without_accepted_result(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "parent-task"
            attempt_dir = parent / "attempts" / "001"
            output = parent / "outputs" / "candidate.png"
            attempt_dir.mkdir(parents=True)
            output.parent.mkdir()
            Image.new("RGB", (40, 40), "white").save(output)
            digest = file_hash(output)
            (attempt_dir / "attempt.json").write_text(
                json.dumps(
                    {
                        "attempt": 1,
                        "status": "rejected",
                        "output": str(output),
                        "output_sha256": digest,
                    }
                ),
                encoding="utf-8",
            )
            error_dir = parent / "attempts" / "002"
            error_dir.mkdir()
            (error_dir / "attempt.json").write_text(
                json.dumps(
                    {
                        "attempt": 2,
                        "status": "error",
                        "output": None,
                        "failures": [
                            {"category": "technical", "note": "network error"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            target, source = recorded_attempt_source(parent, "latest")
            self.assertEqual(target, output.resolve())
            self.assertEqual(source["attempt"], 1)
            self.assertEqual(source["status"], "rejected")
            self.assertFalse((parent / "result.json").exists())

    def test_recorded_candidate_rejects_changed_output_bytes(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "parent-task"
            attempt_dir = parent / "attempts" / "001"
            output = parent / "candidate.png"
            attempt_dir.mkdir(parents=True)
            Image.new("RGB", (20, 20), "white").save(output)
            (attempt_dir / "attempt.json").write_text(
                json.dumps(
                    {
                        "attempt": 1,
                        "status": "rejected",
                        "output": str(output),
                        "output_sha256": "wrong",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                recorded_attempt_source(parent, "latest")

    def test_local_composite_preserves_every_pixel_outside_edit_box(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            candidate = root / "candidate.png"
            output = root / "output.png"
            Image.new("RGB", (100, 80), "red").save(source)
            Image.new("RGB", (40, 40), "blue").save(candidate)
            report = composite_local_edit(
                source,
                candidate,
                output,
                (20, 10, 40, 40),
                (30, 20, 20, 20),
                0,
            )
            self.assertTrue(report["outside_edit_box_preserved"])
            self.assertTrue(outside_edit_box_equal(source, output, (30, 20, 20, 20)))
            with Image.open(output) as image:
                self.assertEqual(image.size, (100, 80))
                self.assertEqual(image.convert("RGB").getpixel((40, 30)), (0, 0, 255))
                self.assertEqual(image.convert("RGB").getpixel((5, 5)), (255, 0, 0))

    def test_retry_stop_counts_only_unchanged_consecutive_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            (task / "attempts" / "001").mkdir(parents=True)
            (task / "attempts" / "002").mkdir(parents=True)
            (task / "prompt.md").write_text("same prompt", encoding="utf-8")
            (task / "reference-manifest.json").write_text("{}", encoding="utf-8")
            for number in ("001", "002"):
                attempt = task / "attempts" / number
                (attempt / "attempt.json").write_text(
                    json.dumps({"status": "error"}), encoding="utf-8"
                )
                (attempt / "prompt.md").write_text("same prompt", encoding="utf-8")
                (attempt / "reference-manifest.json").write_text("{}", encoding="utf-8")
            self.assertEqual(unchanged_consecutive_errors(task), 2)
            (task / "prompt.md").write_text("changed prompt", encoding="utf-8")
            self.assertEqual(unchanged_consecutive_errors(task), 0)

    def test_retry_stop_survives_prompt_changes_after_two_technical_errors(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            for number in ("001", "002"):
                attempt = task / "attempts" / number
                attempt.mkdir(parents=True)
                (attempt / "attempt.json").write_text(
                    json.dumps(
                        {
                            "status": "error",
                            "failures": [
                                {"category": "technical", "note": "network error"}
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                (attempt / "prompt.md").write_text(
                    f"different prompt {number}", encoding="utf-8"
                )
                (attempt / "reference-manifest.json").write_text(
                    json.dumps({"attempt": number}), encoding="utf-8"
                )
            (task / "prompt.md").write_text("third prompt", encoding="utf-8")
            (task / "reference-manifest.json").write_text(
                json.dumps({"attempt": "third"}), encoding="utf-8"
            )
            self.assertEqual(unchanged_consecutive_errors(task), 0)
            self.assertEqual(consecutive_technical_errors(task), 2)

            (task / "attempts" / "003").mkdir()
            (task / "attempts" / "003" / "attempt.json").write_text(
                json.dumps(
                    {
                        "status": "rejected",
                        "failures": [{"category": "composition", "note": "wrong crop"}],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(consecutive_technical_errors(task), 0)

    def test_new_response_window_resets_technical_error_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            old_window = "2026-08-10T20:00:00+08:00"
            new_window = "2026-08-10T20:10:00+08:00"
            attempt = task / "attempts" / "001"
            attempt.mkdir(parents=True)
            (attempt / "attempt.json").write_text(
                json.dumps(
                    {
                        "status": "error",
                        "response_started_at": old_window,
                        "failures": [
                            {"category": "technical", "note": "network error"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(consecutive_technical_errors(task, old_window), 1)
            self.assertEqual(consecutive_technical_errors(task, new_window), 0)


class IntentWorkflowTests(unittest.TestCase):
    def brief(self, intent: str) -> dict:
        return {
            "intent": intent,
            "request": "只收窄犬夜叉右肩",
            "change_request": "只收窄犬夜叉右肩",
            "change_category": "anatomy",
            "medium": "manga",
            "deliverable": "edit" if intent != "new" else "illustration",
            "period_mode": "classic-balanced",
            "aspect_ratio": "4:5",
            "identity_forms": {"犬夜叉": "half-demon-form"},
            "forms_and_costumes": ["犬夜叉: half-demon-form"],
            "scene": "草地双人近景",
            "invariants": ["两只犬耳保持完整", "除右肩外全部区域保持不变"],
        }

    def test_microfix_prompt_is_compact_and_scope_locked(self) -> None:
        manifest = {
            "references": [
                {
                    "role": "target",
                    "item_id": "user-supplied:test",
                    "instructions": "Preserve except for the named local edit.",
                }
            ]
        }
        prompt = compile_prompt(self.brief("microfix"), manifest)
        self.assertIn("Change only `anatomy`", prompt)
        self.assertIn("Do not redesign the whole image", prompt)
        self.assertLess(len(prompt), prompt_limit("microfix"))

    def test_default_latency_budget_targets_only_controllable_phases(self) -> None:
        edit_budget = latency_budget({"intent": "edit"})
        new_budget = latency_budget({"intent": "new"})
        self.assertEqual(edit_budget["pre_generation_target_seconds"], 30)
        self.assertEqual(new_budget["pre_generation_target_seconds"], 90)
        self.assertEqual(edit_budget["post_generation_target_seconds"], 30)
        self.assertEqual(edit_budget["max_technical_retries"], 1)
        self.assertNotIn("response_slo_seconds", edit_budget)
        self.assertNotIn("generation_budget_seconds", edit_budget)

    def test_legacy_latency_budget_maps_to_soft_targets(self) -> None:
        budget = latency_budget(
            {
                "intent": "edit",
                "latency_budget": {
                    "response_slo_seconds": 420,
                    "preparation_budget_seconds": 120,
                    "generation_budget_seconds": 240,
                    "handoff_budget_seconds": 60,
                },
            }
        )
        self.assertEqual(budget["pre_generation_target_seconds"], 120)
        self.assertEqual(budget["post_generation_target_seconds"], 60)
        self.assertNotIn("response_slo_seconds", budget)

    def test_elapsed_seconds_requires_ordered_timezone_timestamps(self) -> None:
        self.assertEqual(
            elapsed_seconds("2026-08-10T20:00:00+08:00", "2026-08-10T20:07:00+08:00"),
            420.0,
        )
        with self.assertRaises(ValueError):
            elapsed_seconds("2026-08-10T20:00:00", "2026-08-10T20:01:00")

    def test_attempt_records_phase_timing_without_total_slo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            started_at = "2026-08-10T20:00:00+08:00"
            generation_started_at = "2026-08-10T20:00:05+08:00"
            recorded_at = "2026-08-10T20:00:25+08:00"
            (task / "brief.json").write_text(
                json.dumps(
                    {
                        "medium": "manga",
                        "intent": "edit",
                        "created_at": started_at,
                        "latency_budget": {
                            "schema_version": 2,
                            "pre_generation_target_seconds": 30,
                            "post_generation_target_seconds": 30,
                            "max_technical_retries": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (task / "reference-manifest.json").write_text(
                json.dumps({"references": []}), encoding="utf-8"
            )
            (task / "response-window.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "started_at": started_at,
                        "pre_generation_started_at": started_at,
                        "generation_started_at": generation_started_at,
                        "pre_generation_seconds": 5.0,
                        "pre_generation_target_seconds": 30,
                        "post_generation_target_seconds": 30,
                    }
                ),
                encoding="utf-8",
            )
            output = task / "candidate.png"
            output.write_bytes(b"candidate")
            arguments = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "rejected",
                "--output",
                str(output),
                "--failure",
                "composition=test",
                "--duration-seconds",
                "10",
            ]
            with (
                patch("sys.argv", arguments),
                patch("record_attempt.now_iso", return_value=recorded_at),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(record_attempt_main(), 0)
            attempt = json.loads(
                (task / "attempts" / "001" / "attempt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(attempt["response_started_at"], started_at)
            self.assertEqual(attempt["generation_seconds"], 10.0)
            self.assertEqual(attempt["pre_generation_seconds"], 5.0)
            self.assertEqual(attempt["post_generation_seconds"], 10.0)
            self.assertEqual(attempt["workflow_overhead_seconds"], 15.0)
            self.assertTrue(attempt["pre_generation_target_met"])
            self.assertTrue(attempt["post_generation_target_met"])
            self.assertIsNone(attempt["response_slo_seconds"])
            self.assertIsNone(attempt["response_slo_met"])
            closed_window = json.loads(
                (task / "response-window.json").read_text(encoding="utf-8")
            )
            self.assertEqual(closed_window["phase"], "recorded")
            self.assertEqual(closed_window["last_attempt"], 1)
            self.assertEqual(closed_window["last_status"], "rejected")

    def test_response_report_includes_average_and_p90(self) -> None:
        summary = duration_summary([60.0, 120.0, 420.0])
        self.assertEqual(summary["average_seconds"], 200.0)
        self.assertEqual(summary["median_seconds"], 120.0)
        self.assertEqual(summary["p90_seconds"], 420.0)

    def test_retry_limit_depends_on_failures_not_elapsed_time(self) -> None:
        self.assertFalse(technical_retry_limit_reached(0, 1))
        self.assertFalse(technical_retry_limit_reached(1, 1))
        self.assertTrue(technical_retry_limit_reached(2, 1))

    def test_prompt_uses_input_order_without_opaque_item_ids(self) -> None:
        manifest = {
            "references": [
                {
                    "role": "style",
                    "item_id": "manga-curated:file:opaquehash",
                    "instructions": "Control manga mark-making only.",
                }
            ]
        }
        prompt = compile_prompt(self.brief("new"), manifest)
        self.assertIn("Input 1 (style)", prompt)
        self.assertNotIn("opaquehash", prompt)

    def test_child_inuyasha_ledger_does_not_inherit_adult_props(self) -> None:
        brief = self.brief("new")
        brief["identity_forms"] = {"犬夜叉": "child-form"}
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("幼童体型", prompt)
        self.assertIn("无言灵念珠", prompt)
        self.assertIn("无铁碎牙", prompt)
        self.assertNotIn("青年体型", prompt)

    def test_prompt_explicitly_translates_cross_medium_content(self) -> None:
        manifest = {
            "references": [
                {
                    "role": "style",
                    "instructions": "Control manga mark-making only.",
                },
                {
                    "role": "content",
                    "instructions": "Control exact visible content only.",
                    "cross_medium": True,
                    "evidence_medium": "tv",
                    "focus": "只参考妖怪张口的阶段",
                },
            ]
        }
        prompt = compile_prompt(self.brief("new"), manifest)
        self.assertIn("Cross-medium content conversion", prompt)
        self.assertIn(
            "translate only `只参考妖怪张口的阶段` from tv into manga", prompt
        )
        self.assertIn("exact-focus content evidence fourth", prompt)

    def test_local_microfix_prompt_uses_compact_prompt_invariants(self) -> None:
        brief = self.brief("microfix")
        brief["invariants"] = ["完整父任务约束" * 200]
        brief["prompt_invariants"] = ["父任务已通过的身份和构图保持不变"]
        brief["local_edit"] = {
            "mode": "crop-composite",
            "edit_box": [30, 40, 50, 60],
            "context_box": [10, 20, 90, 100],
        }
        prompt = compile_prompt(
            brief,
            {
                "references": [
                    {
                        "role": "target",
                        "instructions": "Change only the named local detail.",
                    }
                ]
            },
        )
        self.assertIn("context crop", prompt)
        self.assertNotIn("完整父任务约束", prompt)
        self.assertLess(len(prompt), prompt_limit("microfix"))

    def test_candidate_local_edit_prompt_explains_context_crop(self) -> None:
        brief = self.brief("edit")
        brief["local_edit"] = {
            "mode": "crop-composite",
            "edit_box": [30, 40, 50, 60],
            "context_box": [10, 20, 90, 100],
        }
        prompt = compile_prompt(
            brief,
            {
                "references": [
                    {
                        "role": "target",
                        "instructions": "Change only the named local detail.",
                    }
                ]
            },
        )
        self.assertIn("context crop", prompt)
        self.assertIn("source edit box [30, 40, 50, 60]", prompt)

    def test_candidate_source_validation_binds_target_to_recorded_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tasks = Path(directory)
            parent = tasks / "parent-task"
            child = tasks / "child-task"
            attempt_dir = parent / "attempts" / "001"
            output = parent / "candidate.png"
            attempt_dir.mkdir(parents=True)
            child.mkdir()
            output.write_bytes(b"candidate")
            digest = file_hash(output)
            source = {
                "task_id": "parent-task",
                "attempt": 1,
                "status": "rejected",
                "output": str(output.resolve()),
                "output_sha256": digest,
            }
            (attempt_dir / "attempt.json").write_text(
                json.dumps(
                    {
                        "attempt": 1,
                        "status": "rejected",
                        "output": str(output.resolve()),
                        "output_sha256": digest,
                    }
                ),
                encoding="utf-8",
            )
            brief = {
                "intent": "edit",
                "parent_task_id": "parent-task",
                "candidate_source": source,
                "local_edit": {
                    "mode": "crop-composite",
                    "target": str(output.resolve()),
                },
            }
            references = [
                {
                    "role": "target",
                    "original_path": str(output.resolve()),
                    "content_hash": digest,
                    "source_attempt": source,
                }
            ]
            self.assertEqual(candidate_source_failures(child, brief, references), [])

    def test_identity_ledger_expands_human_form_exclusions(self) -> None:
        brief = self.brief("new")
        brief["identity_forms"] = {"犬夜叉": "human-form"}
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("无头顶犬耳", prompt)
        self.assertIn("不得混入杀生丸", prompt)

    def test_microfix_qa_is_shorter_than_new_qa(self) -> None:
        self.assertLess(
            len(qa_items("manga", "microfix", "anatomy")),
            len(qa_items("manga", "new")),
        )

    def test_construction_is_a_supported_guarded_microfix(self) -> None:
        self.assertIn("construction", CHANGE_CATEGORIES)
        checks = qa_items("manga", "microfix", "construction")
        self.assertTrue(
            any(
                category == "construction" and "悬浮" in check
                for category, check in checks
            )
        )

    def test_new_task_qa_checks_spatial_construction(self) -> None:
        checks = qa_items("manga", "new")
        self.assertTrue(
            any(
                category == "construction" and "承重连接" in check
                for category, check in checks
            )
        )

    def test_new_task_qa_checks_cross_medium_content_leakage(self) -> None:
        checks = qa_items("manga", "new")
        self.assertTrue(
            any(
                category == "process" and "跨媒介 content" in check
                for category, check in checks
            )
        )

    def test_retrieval_result_parses_serial_content_gate(self) -> None:
        evidence = """- Selected-medium result: `INSUFFICIENT`
- Cross-medium fallback result: HIT
"""
        self.assertEqual(
            retrieval_result(evidence, "Selected-medium result"), "INSUFFICIENT"
        )
        self.assertEqual(
            retrieval_result(evidence, "Cross-medium fallback result"), "HIT"
        )

    def test_feedback_rank_is_conservative(self) -> None:
        self.assertEqual(feedback_rank(None), 0.5)
        accepted = feedback_rank(
            {"accepted": 1, "rejected": 0, "total": 1, "smoothed_acceptance": 0.6667}
        )
        rejected = feedback_rank(
            {"accepted": 0, "rejected": 1, "total": 1, "smoothed_acceptance": 0.3333}
        )
        self.assertGreater(accepted, 0.5)
        self.assertLess(rejected, 0.5)

    def test_archived_attempts_do_not_affect_reference_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tasks = Path(directory)
            active_attempt = tasks / "active" / "attempts" / "001"
            archived_attempt = tasks / "archived" / "attempts" / "001"
            active_attempt.mkdir(parents=True)
            archived_attempt.mkdir(parents=True)
            (active_attempt / "attempt.json").write_text(
                json.dumps(
                    {
                        "status": "accepted",
                        "reference_item_ids": ["official:file:active"],
                        "legacy_import": False,
                    }
                ),
                encoding="utf-8",
            )
            (archived_attempt / "attempt.json").write_text(
                json.dumps(
                    {
                        "status": "rejected",
                        "reference_item_ids": ["official:file:archived"],
                        "legacy_import": False,
                    }
                ),
                encoding="utf-8",
            )
            (tasks / "archived" / "archived.json").write_text("{}", encoding="utf-8")
            performance = reference_performance(tasks)
            self.assertIn("official:file:active", performance)
            self.assertNotIn("official:file:archived", performance)

    def test_rejected_attempt_penalizes_only_explicitly_blamed_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tasks = Path(directory)
            rejected = tasks / "rejected" / "attempts" / "001"
            blamed = tasks / "blamed" / "attempts" / "001"
            rejected.mkdir(parents=True)
            blamed.mkdir(parents=True)
            (rejected / "attempt.json").write_text(
                json.dumps(
                    {
                        "status": "rejected",
                        "reference_item_ids": ["official:file:good"],
                        "reference_blame_item_ids": [],
                    }
                ),
                encoding="utf-8",
            )
            (blamed / "attempt.json").write_text(
                json.dumps(
                    {
                        "status": "rejected",
                        "reference_item_ids": [
                            "official:file:good",
                            "official:file:bad",
                        ],
                        "reference_blame_item_ids": ["official:file:bad"],
                    }
                ),
                encoding="utf-8",
            )
            performance = reference_performance(tasks)
            self.assertNotIn("official:file:good", performance)
            self.assertEqual(performance["official:file:bad"]["rejected"], 1)


if __name__ == "__main__":
    unittest.main()
