from __future__ import annotations

import io
import json
import os
import sqlite3
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
from benchmark_reference_retrieval import (
    first_relevant_rank,
    load_dataset,
    metric_summary,
    search_command,
)
from browse_curated_styles import (
    candidate_sort_key,
    hard_facet_filters,
)
from composite_local_microfix import composite_local_edit, outside_edit_box_equal
from continue_art_task import (
    context_box_for,
    continuation_intent,
    inherited_reference_arguments,
    recorded_attempt_source,
    scoped_style_from_ancestry,
)
from image_sheet import build_style_comparison_sheet
from init_art_task import main as init_art_task_main
from init_art_task import qa_items
from plan_art_task import infer_prop_forms
from plan_art_task import main as plan_art_task_main
from preference_profile import write_profile
from prepare_generation_submission import (
    image_record,
    validate_generation_submission,
)
from prepare_reference_set import (
    file_hash,
    image_pixel_hash,
    instruction_for,
    parse_box,
    parse_crop,
    parse_scene_style_coverage,
    render_external_transport,
    render_item,
    source_crop_pixel_hash,
    validate_crop_box,
    validate_reference,
    validate_reference_order,
)
from record_attempt import main as record_attempt_main
from record_attempt import (
    medium_component_failures,
    parse_medium_component_check,
    parse_preview_check,
    preview_handoff_failures,
    requires_manga_medium_components,
)
from reference_feedback_report import duration_summary
from reference_feedback_report import main as reference_feedback_report_main
from start_response_window import main as start_response_window_main
from task_workflow import (
    CHANGE_CATEGORIES,
    CHANGE_SCOPE_SCHEMA_VERSION,
    build_rendering_map,
    character_style_assignments,
    character_style_coverage_failures,
    compile_prompt,
    elapsed_seconds,
    feedback_rank,
    is_split_domain_task,
    latency_budget,
    prompt_limit,
    qa_acceptance_failures,
    reference_performance,
    reference_strategy_failures,
    rendering_map_failures,
    scoped_style_failures,
    strict_character_style_entry,
    style_scope_for_entry,
)
from technical_failures import transport_retry_exhausted
from validate_art_task import (
    candidate_source_failures,
    character_style_view_coverage_failures,
    consecutive_technical_errors,
    crop_derives_from_source,
    identity_focus_failures,
    manifest_style_scope_failure,
    rendering_coverage_failures,
    retrieval_result,
    scene_economy_reference_failures,
    scene_style_coverage_evidence_failures,
    technical_retry_limit_reached,
    unchanged_consecutive_errors,
)
from validate_workflow import identity_ledger_failures
from workflow_common import (
    CONFIG_PATH,
    annotation_shot_types,
    certified_style_anchor_rank,
    eligible_character_style_candidate,
    eligible_reference_roles,
    infer_canonical_scene,
    infer_retrieval_traits,
    infer_structured_metadata,
    infer_subjects,
    infer_tags,
    load_config,
    reference_domain_for,
    repository_root,
    resolve_recorded_path,
    retrieval_relevance,
    retrieval_traits_for,
    retrieval_traits_for_domain,
    style_conflict_subjects,
    visible_files,
)


class PortabilityTests(unittest.TestCase):
    def test_config_resolves_bundled_sources_from_repository_root(self) -> None:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = load_config()
        root = repository_root()
        expected_workflow_root = (
            (root / "workflow" / "reference-workflow").resolve()
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
        with tempfile.TemporaryDirectory() as temp:
            copied_skill = Path(temp) / ".agents/skills/generate-inuyasha-manga-art"
            configured_home = Path(temp) / "portable-package"
            with (
                patch("workflow_common.SKILL_DIR", copied_skill),
                patch.dict(
                    os.environ,
                    {"INUYASHA_WORKFLOW_HOME": str(configured_home)},
                ),
            ):
                self.assertEqual(repository_root(), configured_home.resolve())

    def test_incomplete_checkout_does_not_override_workflow_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            copied_skill = root / ".agents/skills/generate-inuyasha-manga-art"
            false_checkout = copied_skill.parent.parent
            (false_checkout / "workflow/reference-workflow").mkdir(parents=True)
            configured_home = root / "portable-package"
            with (
                patch("workflow_common.SKILL_DIR", copied_skill),
                patch.dict(
                    os.environ,
                    {"INUYASHA_WORKFLOW_HOME": str(configured_home)},
                ),
            ):
                self.assertEqual(repository_root(), configured_home.resolve())


class MetadataTests(unittest.TestCase):
    def test_reference_domains_split_identity_character_style_and_scene(self) -> None:
        self.assertEqual(
            reference_domain_for("official", ["犬夜叉/正面.png"]), "identity"
        )
        self.assertEqual(
            reference_domain_for("manga-curated", ["犬夜叉/人物.png"], ["犬夜叉"]),
            "character-style",
        )
        self.assertEqual(
            reference_domain_for(
                "manga-curated", ["场景/犬夜叉-食骨之井.png"], ["犬夜叉"]
            ),
            "scene",
        )

    def test_domain_scoring_drops_action_from_character_and_scene_queries(self) -> None:
        traits = infer_retrieval_traits("犬夜叉在雨夜屋檐下坐着")
        self.assertEqual(retrieval_traits_for_domain(traits, "character-style"), [])
        self.assertEqual(
            retrieval_traits_for_domain(traits, "scene"),
            ["background:architecture", "background:night", "effect-type:rain"],
        )

    def test_character_style_keeps_view_angle_but_drops_action_and_scene(self) -> None:
        traits = infer_retrieval_traits("戈薇在雨夜侧身托住灯笼")
        self.assertEqual(
            retrieval_traits_for_domain(traits, "character-style"),
            ["view-angle:profile"],
        )

    def test_canonical_scene_inference_is_exact_and_named(self) -> None:
        self.assertEqual(
            infer_canonical_scene("犬夜叉站在食骨之井旁"),
            {"id": "bone-eaters-well", "label": "食骨之井"},
        )
        self.assertEqual(
            infer_canonical_scene("戈薇站在御神木下"),
            {"id": "goshinboku", "label": "御神木"},
        )
        self.assertIsNone(infer_canonical_scene("雨夜普通屋檐"))

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
        traits = infer_retrieval_traits("犬夜叉把双手藏在袖中，在墓碑前挥动铁碎牙")
        self.assertIn("action:sleeve-hidden-hands", traits)
        self.assertIn("action:swing-weapon", traits)
        self.assertIn("content-object:grave", traits)
        self.assertIn("content-object:tessaiga", traits)
        self.assertIn("content-object:robe-sleeve", traits)

    def test_intent_traits_cover_reversed_mother_child_estate_and_first_snow(
        self,
    ) -> None:
        traits = infer_retrieval_traits(
            "幼年犬夜叉和十六夜在雪天的府邸，刚刚开始下雪；"
            "幼年犬夜叉抬头看向天上零星落下的雪花，"
            "十六夜在后面温柔地看着幼年犬夜叉"
        )
        self.assertIn("interaction:mother-child", traits)
        self.assertIn("expression:gentle", traits)
        self.assertIn("background:architecture", traits)
        self.assertIn("effect-type:snow-light", traits)
        self.assertNotIn("effect-type:snow", traits)
        self.assertIn("action:look-up", traits)

    def test_style_conflict_subjects_are_soft_and_request_aware(self) -> None:
        conflicts = style_conflict_subjects("幼年犬夜叉和十六夜在府邸")
        self.assertIn("桔梗", conflicts)
        self.assertIn("戈薇", conflicts)
        self.assertIn("杀生丸", conflicts)
        self.assertNotIn("十六夜", conflicts)
        self.assertNotIn("犬夜叉", conflicts)

    def test_rendering_conflict_penalty_is_explained(self) -> None:
        item = {
            "tags": ["expression:gentle"],
            "filename_terms": [],
            "subjects": ["桔梗", "犬夜叉"],
            "subject_forms": {},
            "shot_types": ["two-shot"],
            "folder_tags": ["桔梗"],
            "eligible_roles": ["rendering"],
            "relative_path": "桔梗/reference.png",
        }
        score, reasons = retrieval_relevance(
            item,
            query_terms=["expression:gentle"],
            shots=["two-shot"],
            penalized_subjects=["桔梗", "戈薇"],
            role="rendering",
        )
        self.assertEqual(score, 2)
        self.assertIn("style identity conflict penalty: 桔梗", reasons)

    def test_rendering_subject_form_preference_is_soft_and_capped(self) -> None:
        item = {
            "tags": [],
            "filename_terms": [],
            "subjects": ["犬夜叉", "十六夜"],
            "subject_forms": {
                "犬夜叉": ["child-form"],
                "十六夜": ["default-form"],
            },
            "shot_types": [],
            "folder_tags": [],
            "eligible_roles": ["rendering"],
            "relative_path": "犬夜叉/mother-child.png",
        }
        score, reasons = retrieval_relevance(
            item,
            preferred_subject_forms=[
                ("犬夜叉", "child-form"),
                ("十六夜", "default-form"),
            ],
            role="rendering",
        )
        self.assertEqual(score, 5)
        self.assertGreater(score, 4)
        self.assertIn("preferred subject-form exact: 犬夜叉=child-form", reasons)

    def test_character_style_preferred_form_keeps_shot_out_of_hard_filters(
        self,
    ) -> None:
        filters = hard_facet_filters(
            reference_domain="character-style",
            role="rendering",
            preferred_subject_forms=[("犬夜叉", "human-form")],
            subjects=[],
            shots=["full-body"],
        )
        self.assertEqual(filters, (("subjects", []),))

    def test_character_style_eligibility_requires_exact_character_and_form(
        self,
    ) -> None:
        requested = [("犬夜叉", "human-form")]
        self.assertTrue(
            eligible_character_style_candidate(
                {
                    "subjects": ["犬夜叉"],
                    "subject_forms": {"犬夜叉": ["human-form"]},
                },
                requested,
            )
        )
        self.assertTrue(
            eligible_character_style_candidate(
                {"subject_forms": {"犬夜叉": ["human-form"]}},
                requested,
            )
        )
        self.assertFalse(
            eligible_character_style_candidate(
                {
                    "subjects": ["犬夜叉"],
                    "subject_forms": {"犬夜叉": ["half-demon-form"]},
                },
                requested,
            )
        )
        self.assertFalse(
            eligible_character_style_candidate(
                {
                    "subjects": ["犬夜叉", "戈薇"],
                    "subject_forms": {
                        "犬夜叉": ["human-form"],
                        "戈薇": ["child-form"],
                    },
                },
                [("犬夜叉", "human-form"), ("戈薇", "default-form")],
            )
        )
        self.assertFalse(
            eligible_character_style_candidate(
                {
                    "subjects": ["七宝"],
                    "subject_forms": {"七宝": ["default-form"]},
                },
                requested,
            )
        )
        self.assertFalse(
            eligible_character_style_candidate(
                {
                    "subjects": ["犬夜叉", "戈薇"],
                    "subject_forms": {
                        "犬夜叉": ["human-form"],
                        "戈薇": ["default-form"],
                    },
                },
                requested,
            )
        )
        for unrequested_subject in ("和尚", "普通人物"):
            with self.subTest(unrequested_subject=unrequested_subject):
                self.assertFalse(
                    eligible_character_style_candidate(
                        {
                            "subjects": ["犬夜叉", unrequested_subject],
                            "subject_forms": {
                                "犬夜叉": ["human-form"],
                                unrequested_subject: ["default-form"],
                            },
                        },
                        requested,
                    )
                )

    def test_candidate_sort_keeps_general_relevance_order(self) -> None:
        candidates = [
            {
                "item_id": "lower",
                "score": 5,
                "certified_style_anchor": False,
                "feedback_rank": 0.0,
                "relative_path": "lower.png",
            },
            {
                "item_id": "higher",
                "score": 12,
                "certified_style_anchor": False,
                "feedback_rank": 0.0,
                "relative_path": "higher.png",
            },
        ]
        ranked = sorted(
            candidates,
            key=candidate_sort_key,
        )
        self.assertEqual([item["item_id"] for item in ranked], ["higher", "lower"])

    def test_scene_rendering_keeps_shot_as_soft_ranking_signal(self) -> None:
        filters = hard_facet_filters(
            reference_domain="scene",
            role="rendering",
            preferred_subject_forms=[],
            subjects=[],
            shots=["wide-shot"],
        )
        self.assertEqual(filters, (("subjects", []),))

    def test_scene_filename_semantics_become_controlled_tags(self) -> None:
        source = {"default_tags": ["manga", "curated"]}
        tags = infer_tags(Path("场景/场景__不适用__远景__山间寺庙__01.png"), source)
        self.assertIn("background:nature", tags)
        self.assertIn("background:architecture", tags)

    def test_shrine_request_retains_specific_and_broad_scene_traits(self) -> None:
        traits = retrieval_traits_for_domain(
            infer_retrieval_traits("深山神社与鸟居"), "scene"
        )
        self.assertIn("content-object:shrine", traits)
        self.assertIn("background:shrine", traits)
        self.assertIn("background:architecture", traits)
        self.assertIn("background:nature", traits)

    def test_scene_material_match_can_outrank_exact_shot(self) -> None:
        base = {
            "filename_terms": [],
            "subjects": [],
            "subject_forms": {},
            "folder_tags": [],
            "content_label": "",
            "relative_path": "",
            "note": "",
            "eligible_roles": ["rendering"],
        }
        terms = [
            "background:architecture",
            "scene-economy:authored-negative-space",
            "detail-falloff:strong",
        ]
        exact_shot_score, _ = retrieval_relevance(
            {
                **base,
                "tags": [
                    "scene-economy:authored-negative-space",
                    "detail-falloff:strong",
                ],
                "shot_types": ["wide-shot"],
            },
            query_terms=terms,
            shots=["wide-shot"],
            role="rendering",
            shot_weight=1,
        )
        material_score, _ = retrieval_relevance(
            {
                **base,
                "tags": [
                    "background:architecture",
                    "scene-economy:authored-negative-space",
                    "detail-falloff:strong",
                ],
                "shot_types": ["close-up"],
            },
            query_terms=terms,
            shots=["wide-shot"],
            role="rendering",
            shot_weight=1,
        )
        self.assertGreater(material_score, exact_shot_score)

    def test_same_form_character_style_outranks_unrelated_exact_shot(self) -> None:
        base = {
            "tags": [],
            "filename_terms": [],
            "folder_tags": [],
            "eligible_roles": ["rendering"],
            "relative_path": "reference.png",
        }
        same_form_score, _ = retrieval_relevance(
            {
                **base,
                "subjects": ["犬夜叉"],
                "subject_forms": {"犬夜叉": ["human-form"]},
                "shot_types": ["close-up"],
            },
            preferred_subject_forms=[("犬夜叉", "human-form")],
            shots=["full-body"],
            role="rendering",
        )
        unrelated_shot_score, _ = retrieval_relevance(
            {
                **base,
                "subjects": ["戈薇"],
                "subject_forms": {"戈薇": ["default-form"]},
                "shot_types": ["full-body"],
            },
            preferred_subject_forms=[("犬夜叉", "human-form")],
            shots=["full-body"],
            role="rendering",
        )
        self.assertGreater(same_form_score, unrelated_shot_score)

    def test_exact_view_angle_outranks_mismatched_camera_distance_anchor(self) -> None:
        base = {
            "filename_terms": [],
            "subjects": ["戈薇"],
            "subject_forms": {"戈薇": ["default-form"]},
            "folder_tags": [],
            "content_label": "",
            "relative_path": "reference.png",
            "note": "",
            "eligible_roles": ["rendering"],
        }
        profile_score, profile_reasons = retrieval_relevance(
            {
                **base,
                "tags": ["view-angle:profile"],
                "shot_types": ["two-shot"],
            },
            preferred_subject_forms=[("戈薇", "default-form")],
            shots=["upper-body"],
            view_angles=["profile"],
            role="rendering",
        )
        front_score, front_reasons = retrieval_relevance(
            {
                **base,
                "tags": ["view-angle:front"],
                "shot_types": ["upper-body"],
            },
            preferred_subject_forms=[("戈薇", "default-form")],
            shots=["upper-body"],
            view_angles=["profile"],
            role="rendering",
        )
        self.assertGreater(profile_score, front_score)
        self.assertIn("view angle exact: profile", profile_reasons)
        self.assertIn("view angle mismatch: profile", front_reasons)
        ambiguous_score, ambiguous_reasons = retrieval_relevance(
            {
                **base,
                "subjects": ["犬夜叉", "戈薇"],
                "tags": ["view-angle:profile"],
                "shot_types": ["two-shot"],
            },
            preferred_subject_forms=[("戈薇", "default-form")],
            shots=["upper-body"],
            view_angles=["profile"],
            role="rendering",
        )
        self.assertLess(ambiguous_score, profile_score)
        self.assertIn(
            "view angle ambiguous across co-occurring subjects: profile",
            ambiguous_reasons,
        )

    def test_single_character_style_prefers_focused_panel_softly(self) -> None:
        base = {
            "tags": [],
            "filename_terms": [],
            "subject_forms": {"犬夜叉": ["half-demon-form"]},
            "shot_types": ["upper-body"],
            "folder_tags": [],
            "eligible_roles": ["rendering"],
            "relative_path": "reference.png",
        }
        focused_score, _ = retrieval_relevance(
            {**base, "subjects": ["犬夜叉"]},
            preferred_subject_forms=[("犬夜叉", "half-demon-form")],
            role="rendering",
        )
        shared_score, shared_reasons = retrieval_relevance(
            {
                **base,
                "subjects": ["犬夜叉", "桔梗"],
                "subject_forms": {
                    "犬夜叉": ["half-demon-form"],
                    "桔梗": ["default-form"],
                },
            },
            preferred_subject_forms=[("犬夜叉", "half-demon-form")],
            role="rendering",
        )
        self.assertGreater(focused_score, shared_score)
        self.assertIn("preferred subject focus: extra subjects present", shared_reasons)

    def test_benchmark_covers_real_reversed_mother_child_rendering_path(self) -> None:
        dataset = load_dataset(
            Path(__file__).resolve().parents[1]
            / "references"
            / "retrieval-benchmark.json"
        )
        case = next(
            case
            for case in dataset["cases"]
            if case["id"] == "child-inuyasha-izayoi-first-snow-rendering"
        )
        self.assertEqual(case["query"]["role"], "rendering")
        self.assertNotIn("subject", case["query"])
        self.assertNotIn("subject_form", case["query"])
        self.assertIn("幼年犬夜叉和十六夜", case["intent_text"])

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
            eligible_reference_roles(["identity"], ["reference-role:content-only"]),
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

    def test_prop_only_official_sheet_satisfies_exact_prop_form(self) -> None:
        row = self.row(
            source="official",
            subjects=["铁碎牙"],
            forms=["transformed-form", "untransformed-form"],
            subject_forms={"铁碎牙": ["transformed-form", "untransformed-form"]},
        )
        validate_reference(
            row,
            "identity",
            "official:tessaiga",
            "manga",
            {"犬夜叉": "half-demon-form", "铁碎牙": "transformed-form"},
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

    def test_style_reference_does_not_inherit_visible_character_form(self) -> None:
        row = self.row(
            source="manga-curated",
            subjects=["犬夜叉", "十六夜"],
            forms=["default-form", "half-demon-form"],
            subject_forms={
                "犬夜叉": ["half-demon-form"],
                "十六夜": ["default-form"],
            },
        )
        validate_reference(
            row,
            "style",
            "manga:mother-child-two-shot",
            "manga",
            {"犬夜叉": "child-form", "十六夜": "default-form"},
        )

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

    def test_long_network_error_exhausts_outer_retry(self) -> None:
        attempt = {
            "status": "error",
            "generation_seconds": 240.0,
            "failures": [
                {
                    "category": "technical",
                    "note": "network error: error sending request to images/edits",
                }
            ],
        }
        self.assertTrue(transport_retry_exhausted(attempt))
        attempt["generation_seconds"] = 30.0
        self.assertFalse(transport_retry_exhausted(attempt))

    def test_start_window_requires_explicit_authorization_after_exhausted_network(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            (task / "attempts" / "001").mkdir(parents=True)
            (task / "brief.json").write_text(
                json.dumps({"intent": "edit"}), encoding="utf-8"
            )
            (task / "attempts" / "001" / "attempt.json").write_text(
                json.dumps(
                    {
                        "attempt": 1,
                        "status": "error",
                        "generation_seconds": 240.0,
                        "failures": [
                            {"category": "technical", "note": "network error"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "sys.argv",
                    ["start_response_window.py", "--task-dir", str(task)],
                ),
                self.assertRaises(SystemExit),
            ):
                start_response_window_main()
            with (
                patch(
                    "sys.argv",
                    [
                        "start_response_window.py",
                        "--task-dir",
                        str(task),
                        "--authorize-network-retry",
                        "--authorization-note",
                        "用户明确要求稍后再试一次",
                    ],
                ),
                patch(
                    "start_response_window.now_iso",
                    return_value="2026-08-15T21:00:00+08:00",
                ),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(start_response_window_main(), 0)
            window = json.loads(
                (task / "response-window.json").read_text(encoding="utf-8")
            )
            self.assertTrue(window["network_retry_authorized"])
            self.assertEqual(window["network_retry_authorized_attempt"], 1)

    def test_submission_rejects_target_hidden_under_new_intent(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            target = task / "target.png"
            Image.new("RGB", (8, 8), "white").save(target)
            started_at = "2026-08-15T21:00:00+08:00"
            (task / "brief.json").write_text(
                json.dumps({"schema_version": 5, "intent": "new"}),
                encoding="utf-8",
            )
            (task / "reference-manifest.json").write_text(
                json.dumps(
                    {"references": [{"role": "target", "rendered_path": str(target)}]}
                ),
                encoding="utf-8",
            )
            prompt = task / "prompt.md"
            prompt.write_text("edit", encoding="utf-8")
            (task / "response-window.json").write_text(
                json.dumps(
                    {
                        "phase": "pre-generation",
                        "started_at": started_at,
                        "pre_generation_started_at": started_at,
                    }
                ),
                encoding="utf-8",
            )
            submission = {
                "schema_version": 1,
                "state": "prepared",
                "response_started_at": started_at,
                "prompt": str(prompt),
                "prompt_sha256": file_hash(prompt),
                "brief_sha256": file_hash(task / "brief.json"),
                "reference_manifest_sha256": file_hash(
                    task / "reference-manifest.json"
                ),
                "images": [image_record(1, "target", target)],
            }
            failures = validate_generation_submission(task, submission)
            self.assertTrue(any("child edit task" in failure for failure in failures))

    def test_submission_snapshot_is_bound_to_persisted_candidate(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            target = task / "target.png"
            generated = task / "generated.png"
            Image.new("RGB", (8, 8), "white").save(target)
            Image.new("RGB", (8, 8), "black").save(generated)
            started_at = "2026-08-15T21:00:00+08:00"
            (task / "brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": 5,
                        "intent": "edit",
                        "medium": "manga",
                        "created_at": started_at,
                    }
                ),
                encoding="utf-8",
            )
            (task / "reference-manifest.json").write_text(
                json.dumps(
                    {"references": [{"role": "target", "rendered_path": str(target)}]}
                ),
                encoding="utf-8",
            )
            prompt = task / "prompt.md"
            prompt.write_text("edit target only", encoding="utf-8")
            (task / "response-window.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "phase": "pre-generation",
                        "started_at": started_at,
                        "pre_generation_started_at": started_at,
                    }
                ),
                encoding="utf-8",
            )
            submission = {
                "schema_version": 1,
                "state": "prepared",
                "response_started_at": started_at,
                "prompt": str(prompt),
                "prompt_sha256": file_hash(prompt),
                "brief_sha256": file_hash(task / "brief.json"),
                "reference_manifest_sha256": file_hash(
                    task / "reference-manifest.json"
                ),
                "endpoint": "https://chatgpt.com/backend-api/codex/images/edits",
                "transport": "manifest-tracked",
                "images": [image_record(1, "target", target)],
                "input_bytes": target.stat().st_size,
            }
            (task / "generation-submission.json").write_text(
                json.dumps(submission), encoding="utf-8"
            )
            with (
                patch(
                    "sys.argv",
                    [
                        "start_response_window.py",
                        "--task-dir",
                        str(task),
                        "--mark-generation-started",
                    ],
                ),
                patch(
                    "start_response_window.now_iso",
                    return_value="2026-08-15T21:00:05+08:00",
                ),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(start_response_window_main(), 0)
            with (
                patch(
                    "sys.argv",
                    [
                        "record_attempt.py",
                        "--task-dir",
                        str(task),
                        "--status",
                        "candidate",
                        "--output",
                        str(generated),
                        "--duration-seconds",
                        "10",
                        "--persist-output",
                        "--preview-check",
                        "identity=pass:face and requested form match official evidence",
                        "--preview-check",
                        "request=pass:requested edit scope is visible",
                        "--preview-check",
                        "medium=pass:line and tone density match selected medium",
                        "--preview-check",
                        "technical=pass:image is complete and artifact free",
                        "--json",
                    ],
                ),
                patch(
                    "record_attempt.now_iso",
                    return_value="2026-08-15T21:00:20+08:00",
                ),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(record_attempt_main(), 0)
            attempt_dir = task / "attempts" / "001"
            attempt = json.loads(
                (attempt_dir / "attempt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(attempt["actual_input_images"][0]["role"], "target")
            self.assertEqual(attempt["actual_input_bytes"], target.stat().st_size)
            self.assertEqual(attempt["preview_checks"][0]["category"], "identity")
            self.assertEqual(attempt["preview_checks"][0]["result"], "pass")
            self.assertTrue(
                Path(attempt["output"]).is_relative_to((task / "outputs").resolve())
            )
            self.assertTrue((attempt_dir / "generation-submission.json").is_file())
            current = json.loads(
                (task / "generation-submission.json").read_text(encoding="utf-8")
            )
            self.assertEqual(current["state"], "recorded")

    def test_continuation_routes_bounded_and_full_canvas_changes(self) -> None:
        self.assertEqual(continuation_intent(None, False), "microfix")
        self.assertEqual(continuation_intent(None, True), "edit")
        self.assertEqual(continuation_intent({"attempt": 1}, False), "edit")

    def test_continuation_finds_nearest_matching_style_domain_in_parent_chain(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tasks = Path(directory)
            root = tasks / "root-task"
            child = tasks / "child-task"
            root.mkdir()
            child.mkdir()
            (root / "brief.json").write_text(
                json.dumps({"task_id": "root-task", "parent_task_id": None}),
                encoding="utf-8",
            )
            (root / "reference-manifest.json").write_text(
                json.dumps(
                    {
                        "references": [
                            {
                                "role": "style",
                                "item_id": "character-style",
                                "style_scope": "character",
                            },
                            {
                                "role": "style",
                                "item_id": "scene-style",
                                "style_scope": "scene",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (child / "brief.json").write_text(
                json.dumps({"task_id": "child-task", "parent_task_id": "root-task"}),
                encoding="utf-8",
            )
            (child / "reference-manifest.json").write_text(
                json.dumps(
                    {
                        "references": [
                            {
                                "role": "style",
                                "item_id": "child-scene-style",
                                "style_scope": "scene",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            selected, source_task = scoped_style_from_ancestry(
                child, tasks, "character"
            )
            self.assertEqual(selected["item_id"], "character-style")
            self.assertEqual(source_task, root.resolve())

    def test_continuation_derives_legacy_style_scope_from_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tasks = Path(directory)
            parent = tasks / "legacy-parent"
            parent.mkdir()
            (parent / "brief.json").write_text(
                json.dumps({"task_id": "legacy-parent", "parent_task_id": None}),
                encoding="utf-8",
            )
            (parent / "reference-manifest.json").write_text(
                json.dumps(
                    {"references": [{"role": "style", "item_id": "legacy-style"}]}
                ),
                encoding="utf-8",
            )
            connection = sqlite3.connect(":memory:")
            connection.row_factory = sqlite3.Row
            connection.execute(
                "CREATE TABLE items (item_id TEXT PRIMARY KEY, reference_domain TEXT)"
            )
            connection.execute(
                "CREATE TABLE item_aliases (alias_id TEXT PRIMARY KEY, item_id TEXT)"
            )
            connection.execute(
                "INSERT INTO items VALUES ('legacy-style', 'character-style')"
            )
            selected, source_task = scoped_style_from_ancestry(
                parent, tasks, "character", connection
            )
            connection.close()
            self.assertEqual(selected["item_id"], "legacy-style")
            self.assertEqual(source_task, parent.resolve())

    def test_style_scope_uses_manifest_then_catalog_domain_compatibility(self) -> None:
        self.assertEqual(style_scope_for_entry({"style_scope": "scene"}), "scene")
        self.assertEqual(
            style_scope_for_entry({"reference_domain": "character-style"}),
            "character",
        )
        self.assertIsNone(style_scope_for_entry({"reference_domain": "identity"}))
        self.assertEqual(style_scope_for_entry({}, "character-style"), "character")
        self.assertIsNone(
            style_scope_for_entry({"style_scope": "invalid"}, "character-style")
        )

    def test_manifest_style_scope_preserves_legacy_but_enforces_current_records(
        self,
    ) -> None:
        legacy = {"role": "style", "item_id": "legacy-character-style"}
        self.assertIsNone(
            manifest_style_scope_failure(legacy, "character", require_explicit=False)
        )
        current_failure = manifest_style_scope_failure(
            legacy, "character", require_explicit=True
        )
        self.assertIsNotNone(current_failure)
        self.assertIn("expected character", current_failure)
        wrong = {
            "role": "style",
            "item_id": "wrong-scene-style",
            "style_scope": "scene",
        }
        self.assertIsNotNone(
            manifest_style_scope_failure(wrong, "character", require_explicit=False)
        )
        correct = {
            "role": "style",
            "item_id": "current-character-style",
            "style_scope": "character",
        }
        self.assertIsNone(
            manifest_style_scope_failure(correct, "character", require_explicit=True)
        )


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
        self.assertIn("Do not drift toward extra", prompt)
        self.assertIn("strip away identity-critical", prompt)
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
            (task / "prompt.md").write_text("compiled prompt", encoding="utf-8")
            submitted = task / "submitted.md"
            submitted.write_text("exact generator prompt", encoding="utf-8")
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
                "candidate",
                "--output",
                str(output),
                "--submitted-prompt",
                str(submitted),
                "--duration-seconds",
                "10",
                "--preview-check",
                "identity=pass:face and requested form match official evidence",
                "--preview-check",
                "request=pass:requested scene and moment are present",
                "--preview-check",
                "medium=pass:line and tone density match selected medium",
                "--preview-check",
                "technical=pass:image is complete and artifact free",
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
            self.assertEqual(attempt["status"], "candidate")
            self.assertEqual(attempt["submitted_prompt_source"], "explicit")
            self.assertTrue(attempt["submitted_prompt_differs_from_compiled"])
            attempt_dir = task / "attempts" / "001"
            self.assertEqual(
                attempt["brief_sha256"],
                file_hash(attempt_dir / "brief.json"),
            )
            self.assertEqual(
                attempt["reference_manifest_sha256"],
                file_hash(attempt_dir / "reference-manifest.json"),
            )
            self.assertEqual(
                (attempt_dir / "submitted-prompt.md").read_text(encoding="utf-8"),
                "exact generator prompt",
            )
            closed_window = json.loads(
                (task / "response-window.json").read_text(encoding="utf-8")
            )
            self.assertEqual(closed_window["phase"], "recorded")
            self.assertEqual(closed_window["last_attempt"], 1)
            self.assertEqual(closed_window["last_status"], "candidate")

    def test_response_report_includes_average_and_p90(self) -> None:
        summary = duration_summary([60.0, 120.0, 420.0])
        self.assertEqual(summary["average_seconds"], 200.0)
        self.assertEqual(summary["median_seconds"], 120.0)
        self.assertEqual(summary["p90_seconds"], 420.0)

    def test_candidate_handoff_requires_four_unique_passing_checks(self) -> None:
        checks = [
            parse_preview_check("identity=pass:face and form match"),
            parse_preview_check("request=pass:requested moment is present"),
            parse_preview_check("medium=pass:economical manga marks are present"),
            parse_preview_check("technical=pass:image is complete"),
        ]
        self.assertEqual(preview_handoff_failures("candidate", checks), [])
        self.assertTrue(
            any(
                "missing blocking preview checks" in failure
                for failure in preview_handoff_failures("candidate", checks[:1])
            )
        )
        failed = [
            *checks[:2],
            parse_preview_check("medium=fail:rendering is too polished"),
            checks[3],
        ]
        self.assertTrue(
            any(
                "failed blocking preview checks" in failure
                for failure in preview_handoff_failures("candidate", failed)
            )
        )
        warning = [
            checks[0],
            checks[1],
            parse_preview_check(
                "medium=warning:foreground marks are locally dense but manga masses dominate"
            ),
            checks[3],
        ]
        self.assertEqual(preview_handoff_failures("candidate", warning), [])
        misplaced_warning = [
            parse_preview_check("identity=warning:face is somewhat ambiguous"),
            *checks[1:],
        ]
        self.assertTrue(
            any(
                "only non-blocking for medium" in failure
                for failure in preview_handoff_failures("candidate", misplaced_warning)
            )
        )

    def test_face_led_new_task_requires_crop_from_unmatched_setting_sheet(self) -> None:
        brief = {
            "schema_version": 5,
            "intent": "new",
            "shot": "medium-shot",
        }
        row = {
            "item_id": "official:file:human-sheet",
            "tags": json.dumps(["official", "setting-sheet"]),
            "shot_types": json.dumps([]),
        }
        failures = identity_focus_failures(brief, row, {"crop_box": None})
        self.assertEqual(len(failures), 1)
        self.assertIn("smallest task-local crop", failures[0])
        self.assertEqual(
            identity_focus_failures(
                brief,
                row,
                {"crop_box": [10, 10, 100, 100], "focus": "人形态脸部"},
            ),
            [],
        )

    def test_declared_profile_requires_matching_identity_or_focused_crop(self) -> None:
        brief = {
            "schema_version": 5,
            "intent": "new",
            "shot": "upper-body",
            "view_angle": "profile",
        }
        row = {
            "item_id": "official:file:front-kagome",
            "tags": json.dumps(["official", "setting-sheet", "view-angle:front"]),
            "shot_types": json.dumps(["upper-body"]),
        }
        failures = identity_focus_failures(brief, row, {"crop_box": None})
        self.assertEqual(len(failures), 1)
        self.assertIn("requested view angle profile", failures[0])
        self.assertEqual(
            identity_focus_failures(
                brief,
                row,
                {"crop_box": [10, 10, 100, 100], "focus": "戈薇侧脸"},
            ),
            [],
        )

    def test_declared_profile_blocks_mismatched_character_style(self) -> None:
        brief = {
            "schema_version": 5,
            "intent": "new",
            "view_angle": "profile",
            "characters": ["戈薇"],
        }
        front = {
            "item_id": "manga-curated:file:front-kagome",
            "reference_domain": "character-style",
            "subjects": json.dumps(["戈薇"]),
            "tags": json.dumps(["view-angle:front"]),
            "shot_types": json.dumps(["upper-body"]),
        }
        profile = {
            **front,
            "item_id": "manga-curated:file:profile-kagome",
            "tags": json.dumps(["view-angle:profile"]),
        }
        entry = {"role": "style"}
        self.assertEqual(
            len(character_style_view_coverage_failures(brief, [(front, entry)])),
            1,
        )
        self.assertEqual(
            character_style_view_coverage_failures(brief, [(profile, entry)]),
            [],
        )
        general_profile = {
            **profile,
            "subjects": json.dumps(["珊瑚"]),
        }
        self.assertEqual(
            character_style_view_coverage_failures(brief, [(general_profile, entry)]),
            [],
        )
        ambiguous = {
            **profile,
            "subjects": json.dumps(["犬夜叉", "戈薇"]),
        }
        ambiguous_failures = character_style_view_coverage_failures(
            brief, [(ambiguous, entry)]
        )
        self.assertEqual(len(ambiguous_failures), 1)
        self.assertIn("multi-character panel", ambiguous_failures[0])
        self.assertEqual(
            character_style_view_coverage_failures(
                brief,
                [
                    (
                        ambiguous,
                        {
                            "role": "style",
                            "crop_box": [10, 10, 80, 100],
                            "focus": "戈薇侧脸",
                        },
                    )
                ],
            ),
            [],
        )
        self.assertEqual(
            len(
                character_style_view_coverage_failures(
                    brief,
                    [
                        (
                            ambiguous,
                            {
                                "role": "style",
                                "crop_box": [10, 10, 80, 100],
                                "focus": "",
                            },
                        )
                    ],
                )
            ),
            1,
        )
        self.assertEqual(
            character_style_view_coverage_failures(
                brief, [(front, entry), (general_profile, entry)]
            ),
            [],
        )

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

    def test_new_manga_prompt_rejects_polished_illustration_finish(self) -> None:
        prompt = compile_prompt(self.brief("new"), {"references": []})
        self.assertIn("late-1990s serialized black-and-white manga", prompt)
        self.assertIn("not a polished monochrome illustration", prompt)
        self.assertIn("Manga finish calibration", prompt)
        self.assertIn("selected character and scene references", prompt)
        self.assertIn("Preserve requested scene phenomena", prompt)
        self.assertIn("under-rendered coloring-book outline", prompt)
        self.assertIn("identity-bearing eye shape", prompt)
        self.assertIn("Economy means selecting the right marks", prompt)
        self.assertNotIn("continuous shine bands", prompt)
        self.assertNotIn("wet reflections", prompt)

    def test_explicit_two_hand_request_compiles_visible_contact_topology(self) -> None:
        brief = self.brief("new")
        brief["request"] = "十六夜用双手和布巾替幼年犬夜叉擦拭湿发"
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("Named contact topology", prompt)
        self.assertIn("exactly two distinct, visible hands", prompt)
        self.assertIn("Both hands must participate", prompt)
        self.assertIn("every named prop and body-part contact", prompt)

    def test_wide_manga_prompt_uses_scene_economy_instead_of_generic_guard(
        self,
    ) -> None:
        brief = self.brief("new")
        brief["shot"] = "wide-shot"
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("serialized manga establishing shot", prompt)
        self.assertIn("single borderless serialized-manga panel", prompt)
        self.assertNotIn("; illustration;", prompt)
        self.assertIn("authored white-paper intervals", prompt)
        self.assertIn("contiguous paper-white fields", prompt)
        self.assertIn("keep them unfilled", prompt)
        self.assertIn("every successive depth layer must lose internal marks", prompt)
        self.assertIn("finite narrative budget", prompt)
        self.assertIn("detail falls away clearly", prompt)
        self.assertIn("same economy consistently", prompt)
        self.assertIn("leave surface finish deliberately selective", prompt)
        self.assertIn("Preserve recognizable materials, weather, and light", prompt)
        self.assertNotIn("Do not draw individual leaves", prompt)
        self.assertNotIn("repeated roof tiles", prompt)
        self.assertIn("uniform fine texture", prompt)
        self.assertIn("the rendering fails", prompt)
        self.assertIn("Complete objects and correct perspective do not excuse", prompt)
        self.assertNotIn("empty architecture", prompt)
        self.assertNotIn("Economy means selecting the right marks", prompt)

    def test_wide_manga_qa_checks_economy_and_spatial_structure(self) -> None:
        checks = qa_items("manga", "new", shot="wide-shot")
        self.assertTrue(
            any(
                category == "medium"
                and "连续可见的纸白开阔面" in check
                and "每一层远景明显减少内部线条" in check
                for category, check in checks
            )
        )
        self.assertTrue(
            any(
                category == "composition" and "未绘区域" in check
                for category, check in checks
            )
        )

    def test_manga_style_authority_includes_scene_simplification(self) -> None:
        instruction = instruction_for(
            "style", "manga", focus="脸、头发、衣褶与服装深浅层级"
        )
        self.assertIn("background omission", instruction)
        self.assertIn("material simplification", instruction)
        self.assertIn("distance-based detail falloff", instruction)
        self.assertIn("face, hair, fabric, and fold mark-making", instruction)
        self.assertIn("relative paper-white, flat-black", instruction)
        self.assertIn("garment construction", instruction)
        self.assertIn("Exact focus: 脸、头发、衣褶与服装深浅层级", instruction)

    def test_manga_style_authority_is_scoped_by_reference_domain(self) -> None:
        character = instruction_for(
            "style", "manga", reference_domain="character-style"
        )
        scene = instruction_for("style", "manga", reference_domain="scene")
        self.assertIn("character rendering", character)
        self.assertNotIn("scene rendering", character)
        self.assertIn("scene rendering", scene)
        self.assertIn("Do not copy visible people", scene)

    def test_canonical_scene_style_authority_requires_explicit_coverage(self) -> None:
        hit = instruction_for(
            "content",
            "manga",
            focus="食骨之井结构",
            reference_domain="scene",
            content_kind="scene",
            scene_style_coverage="HIT",
        )
        insufficient = instruction_for(
            "content",
            "manga",
            focus="食骨之井结构",
            reference_domain="scene",
            content_kind="scene",
            scene_style_coverage="INSUFFICIENT",
        )
        self.assertIn("Human inspection recorded", hit)
        self.assertNotIn("Human inspection recorded", insufficient)
        self.assertEqual(
            parse_scene_style_coverage("manga-curated:file:abc=hit"),
            ("manga-curated:file:abc", "HIT"),
        )
        with self.assertRaises(ArgumentTypeError):
            parse_scene_style_coverage("manga-curated:file:abc=MISS")

    def test_manga_prompt_bridges_official_garment_to_style_values(self) -> None:
        prompt = compile_prompt(self.brief("new"), {"references": []})
        self.assertIn("canonical garment component", prompt)
        self.assertIn("paper-white, flat-black", prompt)
        self.assertIn("Never copy the style source's costume design", prompt)

    def test_manga_qa_checks_character_marks_and_garment_values(self) -> None:
        checks = qa_items("manga", "new")
        self.assertTrue(any("origin-photos" in check for _, check in checks))
        self.assertTrue(any("纸白、整块黑" in check for _, check in checks))

    def test_new_task_persists_explicit_shot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "init_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "wide-scene-test",
                "--medium",
                "manga",
                "--request",
                "废弃神社远景",
                "--identity-form",
                "犬夜叉=half-demon-form",
                "--shot",
                "wide-shot",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(init_art_task_main(), 0)
            task_dir = Path(output.getvalue().strip().splitlines()[-1])
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["shot"], "wide-shot")
            self.assertIn(
                "serialized manga establishing shot",
                (task_dir / "prompt.md").read_text(encoding="utf-8"),
            )
            evidence = (task_dir / "evidence-log.md").read_text(encoding="utf-8")
            self.assertIn("- Character mark-making coverage:", evidence)
            self.assertIn("- Garment value hierarchy coverage:", evidence)
            qa = json.loads((task_dir / "qa.json").read_text(encoding="utf-8"))
            self.assertEqual(qa["schema_version"], 2)
            self.assertEqual(
                brief["reference_strategy"],
                {
                    "schema_version": 1,
                    "mode": "split-domain",
                    "required_style_scopes": ["character", "scene"],
                    "canonical_scene_style": "coverage-gated",
                },
            )
            self.assertTrue(is_split_domain_task(brief, qa))
            self.assertEqual(reference_strategy_failures(brief), [])
            self.assertEqual(
                [row["id"] for row in qa["dimensions"]],
                [
                    "character_identity",
                    "character_style",
                    "scene_identity",
                    "scene_style",
                    "action_request",
                    "composition_integration",
                ],
            )

    def test_new_task_persists_view_angle_separately_from_shot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "init_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "kagome-profile-fields",
                "--medium",
                "manga",
                "--request",
                "戈薇侧身托住灯笼",
                "--identity-form",
                "戈薇=default-form",
                "--shot",
                "upper-body",
                "--view-angle",
                "profile",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(init_art_task_main(), 0)
            task_dir = Path(output.getvalue().strip().splitlines()[-1])
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["shot"], "upper-body")
            self.assertEqual(brief["view_angle"], "profile")
            prompt = (task_dir / "prompt.md").read_text(encoding="utf-8")
            self.assertIn("Camera distance: upper-body", prompt)
            self.assertIn("character view angle: profile", prompt)

    def test_six_dimension_qa_blocks_pending_and_requires_notes(self) -> None:
        dimension_ids = [
            "character_identity",
            "character_style",
            "scene_identity",
            "scene_style",
            "action_request",
            "composition_integration",
        ]
        qa = {
            "schema_version": 2,
            "dimensions": [
                {"id": dimension_id, "status": "pending", "note": ""}
                for dimension_id in dimension_ids
            ],
            "checks": [
                {
                    "category": "technical",
                    "check": "技术完整",
                    "status": "pending",
                    "note": "",
                }
            ],
        }
        self.assertTrue(qa_acceptance_failures(qa))
        duplicate = json.loads(json.dumps(qa))
        duplicate["dimensions"].append(
            {
                "id": "character_identity",
                "status": "pass",
                "note": "后一条重复记录",
            }
        )
        duplicate_failures = qa_acceptance_failures(duplicate)
        self.assertTrue(
            any("exactly 6 rows" in failure for failure in duplicate_failures)
        )
        self.assertTrue(
            any("duplicate IDs" in failure for failure in duplicate_failures)
        )
        malformed = json.loads(json.dumps(qa))
        malformed["dimensions"][0]["id"] = ["character_identity"]
        malformed_failures = qa_acceptance_failures(malformed)
        self.assertTrue(
            any("IDs must be strings" in failure for failure in malformed_failures)
        )
        self.assertEqual(qa_acceptance_failures([]), ["qa must be an object"])
        for row in qa["dimensions"]:
            row.update(status="pass", note="已全尺寸检查")
        qa["checks"][0].update(status="pass", note="无技术缺陷")
        self.assertEqual(qa_acceptance_failures(qa), [])
        qa["dimensions"][3].update(
            status="warning", note="场景局部偏密但仍保持原作漫画第一印象"
        )
        qa["checks"][0].update(
            category="medium",
            status="warning",
            note="前景略密但黑白块和网点层级仍正确",
        )
        self.assertEqual(qa_acceptance_failures(qa), [])
        qa["dimensions"][0].update(status="warning", note="人物身份不能以 warning 放行")
        self.assertTrue(
            any(
                "warning is not allowed" in failure
                for failure in qa_acceptance_failures(qa)
            )
        )

    def test_scene_style_coverage_evidence_must_match_manifest_and_have_basis(
        self,
    ) -> None:
        contradictory = """- Scene identity result: HIT
- Scene style coverage: INSUFFICIENT
- Coverage basis: 屋顶、雨线与留白不足
"""
        failures = scene_style_coverage_evidence_failures(contradictory, "HIT", "HIT")
        self.assertTrue(any("does not match" in failure for failure in failures))

        placeholder = """- Scene identity result: HIT
- Scene style coverage: HIT
- Coverage basis: record visible materials, weather, black-white mass
"""
        failures = scene_style_coverage_evidence_failures(placeholder, "HIT", "HIT")
        self.assertTrue(any("concrete" in failure for failure in failures))

        inspected = """- Scene identity result: HIT
- Scene style coverage: HIT
- Coverage basis: 井栏木纹、雨幕留白和远近细节均可见
"""
        self.assertEqual(
            scene_style_coverage_evidence_failures(inspected, "HIT", "HIT"), []
        )
        missing = """- Scene identity result: MISS
- Scene style coverage: N/A
- Coverage basis: N/A
"""
        self.assertEqual(
            scene_style_coverage_evidence_failures(missing, "MISS", None), []
        )

    def test_initializer_requires_and_persists_style_change_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "init_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "missing-tone-scope",
                "--medium",
                "manga",
                "--deliverable",
                "edit",
                "--intent",
                "edit",
                "--request",
                "恢复犬夜叉深色衣服",
                "--change-category",
                "tone",
                "--change-request",
                "恢复犬夜叉深色衣服",
            ]
            with (
                patch("sys.argv", arguments),
                self.assertRaisesRegex(SystemExit, "require --change-scope"),
            ):
                init_art_task_main()

            arguments.extend(["--change-scope", "character"])
            arguments[4] = "character-tone-scope"
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(init_art_task_main(), 0)
            task_dir = Path(output.getvalue().strip().splitlines()[-1])
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["change_scope"], "character")
            self.assertEqual(
                brief["change_scope_schema_version"], CHANGE_SCOPE_SCHEMA_VERSION
            )
            evidence = (task_dir / "evidence-log.md").read_text(encoding="utf-8")
            self.assertIn("Change scope: `character`", evidence)

    def test_new_task_persists_prop_topology_and_material_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "init_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "tessaiga-material-test",
                "--medium",
                "manga",
                "--request",
                "犬夜叉在森林挥动变化后的铁碎牙",
                "--identity-form",
                "犬夜叉=half-demon-form",
                "--prop-form",
                "铁碎牙=transformed-form",
                "--scene-material",
                "树干树皮与聚类树叶",
                "--shot",
                "action",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(init_art_task_main(), 0)
            task_dir = Path(output.getvalue().strip().splitlines()[-1])
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["props"], ["铁碎牙"])
            self.assertEqual(brief["prop_forms"]["铁碎牙"], "transformed-form")
            self.assertEqual(brief["dominant_scene_materials"], ["树干树皮与聚类树叶"])
            prompt = (task_dir / "prompt.md").read_text(encoding="utf-8")
            self.assertIn("Canonical prop requirements", prompt)
            self.assertIn("缠绕刀柄 → 圆形护手 → 单一连续宽刃 → 刀尖", prompt)
            self.assertIn("刀身×1", prompt)
            self.assertIn("树干树皮与聚类树叶", prompt)
            self.assertIn("not separate detailing targets", prompt)
            evidence = (task_dir / "evidence-log.md").read_text(encoding="utf-8")
            self.assertIn("Dominant material rendering coverage", evidence)

    def test_planner_infers_prop_form_from_ledger_data(self) -> None:
        self.assertEqual(
            infer_prop_forms("犬夜叉在森林中挥动变化后的铁碎牙"),
            [("铁碎牙", "transformed-form")],
        )
        with self.assertRaises(SystemExit):
            infer_prop_forms("犬夜叉看着铁碎牙")
        self.assertEqual(
            infer_prop_forms("犬夜叉挥动未变化的铁碎牙"),
            [("铁碎牙", "untransformed-form")],
        )
        self.assertEqual(
            infer_prop_forms("犬夜叉拿着破刀形态的铁碎牙战斗"),
            [("铁碎牙", "untransformed-form")],
        )

    def test_continuity_plan_has_shotless_fallback_without_identity_filter(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "plan_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "continuity-fallback-test",
                "--request",
                "犬夜叉走进森林远景",
                "--identity-form",
                "犬夜叉=half-demon-form",
                "--shot",
                "wide-shot",
                "--continuity",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(plan_art_task_main(), 0)
            result = json.loads(output.getvalue())
            plan = json.loads(
                Path(result["retrieval_plan"]).read_text(encoding="utf-8")
            )
            task_dir = Path(result["task_dir"])
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
            qa = json.loads((task_dir / "qa.json").read_text(encoding="utf-8"))
            self.assertTrue(is_split_domain_task(brief, qa))
            continuity = next(
                layer
                for layer in plan["layers"]
                if layer.get("source") == "selected-output"
            )
            primary = continuity["primary_commands"][0]
            fallback = continuity["fallback_without_shot"][0]
            self.assertIn("--shot", primary)
            self.assertNotIn("--shot", fallback)
            self.assertNotIn("--subject", fallback)
            self.assertNotIn("--form", fallback)

    def test_canonical_scene_plan_has_explicit_style_coverage_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "plan_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "canonical-scene-gate-test",
                "--request",
                "人类形态犬夜叉站在食骨之井旁",
                "--identity-form",
                "犬夜叉=human-form",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(plan_art_task_main(), 0)
            result = json.loads(output.getvalue())
            plan = json.loads(
                Path(result["retrieval_plan"]).read_text(encoding="utf-8")
            )
            identity_layer = next(
                layer
                for layer in plan["layers"]
                if layer.get("role") == "canonical-scene"
            )
            style_layer = next(
                layer
                for layer in plan["layers"]
                if layer.get("role") == "scene-style-fallback"
            )
            self.assertEqual(
                identity_layer["coverage_gate"]["allowed_values"],
                ["HIT", "INSUFFICIENT"],
            )
            self.assertIn("scene_style_coverage", style_layer["run_when"][1])
            command = style_layer["primary_commands"][0]
            self.assertIn("--exclude-exact-term", command)
            self.assertIn("scene-id:bone-eaters-well", command)

    def test_wide_shot_adds_positive_scene_economy_traits(self) -> None:
        traits = retrieval_traits_for("雨夜神社", "wide-shot", medium="manga")
        self.assertIn("scene-economy:authored-negative-space", traits)
        self.assertIn("detail-falloff:strong", traits)
        self.assertEqual(
            parse_trait("scene-economy=authored-negative-space"),
            "scene-economy:authored-negative-space",
        )
        self.assertEqual(
            parse_trait("style-anchor=certified"),
            "style-anchor:certified",
        )
        self.assertNotIn(
            "scene-economy:authored-negative-space",
            retrieval_traits_for("雨夜神社", "wide-shot", medium="tv"),
        )

    def test_certified_style_anchor_is_only_a_rendering_tie_breaker(self) -> None:
        item = {"tags": ["style-anchor:certified"]}
        self.assertEqual(
            certified_style_anchor_rank(
                item, role="rendering", reference_domain="character-style"
            ),
            1,
        )
        self.assertEqual(
            certified_style_anchor_rank(
                item, role="content", reference_domain="character-style"
            ),
            0,
        )
        self.assertEqual(
            certified_style_anchor_rank(
                item, role="rendering", reference_domain="identity"
            ),
            0,
        )

    def test_rendering_map_tracks_character_scene_depth_and_values(self) -> None:
        brief = {
            "medium": "manga",
            "intent": "new",
            "shot": "wide-shot",
            "dominant_scene_materials": ["石阶", "巨树"],
            "retrieval_traits": [
                "scene-economy:authored-negative-space",
                "detail-falloff:strong",
            ],
        }
        rendering_map = build_rendering_map(brief)
        self.assertEqual(rendering_map["schema_version"], 1)
        self.assertEqual(rendering_map["character"]["authority"], "character-style")
        self.assertEqual(rendering_map["scene"]["authority"], "scene-style")
        self.assertIn("石阶, 巨树", rendering_map["scene"]["focal_plane"])
        self.assertIn("successive depth layer", rendering_map["scene"]["far_plane"])
        self.assertEqual(
            rendering_map_failures({**brief, "rendering_map": rendering_map}), []
        )
        broken = json.loads(json.dumps(rendering_map))
        broken["value_hierarchy"]["flat_black"] = ""
        self.assertIn(
            "brief.rendering_map.value_hierarchy.flat_black must be a non-empty string",
            rendering_map_failures({**brief, "rendering_map": broken}),
        )

    def test_compiled_prompt_uses_stored_rendering_map(self) -> None:
        brief = {
            "medium": "manga",
            "intent": "new",
            "request": "犬夜叉站在雨后石阶上",
            "scene": "雨后石阶",
            "shot": "wide-shot",
            "deliverable": "illustration",
            "aspect_ratio": "4:5",
            "period_mode": "classic-balanced",
            "identity_forms": {"犬夜叉": "half-demon-form"},
            "character_style_targets": {"犬夜叉": "half-demon-form"},
            "prop_forms": {},
            "invariants": ["不添加文字"],
            "dominant_scene_materials": ["石阶", "雨幕"],
            "retrieval_traits": [
                "scene-economy:authored-negative-space",
                "detail-falloff:strong",
            ],
        }
        brief["rendering_map"] = build_rendering_map(brief)
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("Scene-aware rendering map:", prompt)
        self.assertIn("石阶, 雨幕", prompt)
        self.assertIn("Values: paper white", prompt)

    def test_style_comparison_sheet_locks_candidate_and_style_hashes(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "task"
            references = task / "references"
            references.mkdir(parents=True)
            candidate = task / "candidate.png"
            style = references / "style.png"
            Image.new("RGB", (80, 120), "white").save(candidate)
            Image.new("RGB", (120, 80), "black").save(style)
            brief = {
                "task_id": "comparison-test",
                "medium": "manga",
                "intent": "edit",
                "rendering_map": build_rendering_map(
                    {
                        "medium": "manga",
                        "intent": "edit",
                        "change_category": "medium",
                        "change_scope": "character",
                        "shot": "upper-body",
                    }
                ),
            }
            (task / "brief.json").write_text(
                json.dumps(brief, ensure_ascii=False), encoding="utf-8"
            )
            (task / "reference-manifest.json").write_text(
                json.dumps(
                    {
                        "references": [
                            {
                                "order": 2,
                                "role": "style",
                                "style_scope": "character",
                                "item_id": "manga-curated:file:test",
                                "rendered_path": str(style),
                                "content_hash": file_hash(style),
                                "focus": "face, hair, and fabric grouping",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            sheet, sidecar = build_style_comparison_sheet(task, candidate)
            self.assertTrue(sheet.is_file())
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(metadata["candidate"]["sha256"], file_hash(candidate))
            self.assertEqual(metadata["style_rows"][0]["sha256"], file_hash(style))
            self.assertEqual(metadata["style_rows"][0]["style_scope"], "character")

    def test_environment_dominant_medium_shot_adds_scene_economy_traits(self) -> None:
        traits = retrieval_traits_for(
            "雨夜檐下，人物看着雨幕，木屋屋顶占据背景",
            "medium-shot",
            medium="manga",
        )
        self.assertIn("background:architecture", traits)
        self.assertIn("background:night", traits)
        self.assertIn("effect-type:rain", traits)
        self.assertIn("scene-economy:authored-negative-space", traits)
        self.assertIn("detail-falloff:strong", traits)

    def test_dense_fog_full_body_adds_mist_and_scene_economy_traits(self) -> None:
        traits = retrieval_traits_for(
            "雾中携刀前行，黑发犬夜叉独自穿过浓雾，姿态谨慎贴近地面",
            "full-body",
            medium="manga",
        )
        self.assertIn("effect-type:mist", traits)
        self.assertIn("scene-economy:authored-negative-space", traits)
        self.assertIn("detail-falloff:strong", traits)

    def test_current_character_style_assignment_requires_exact_form_per_character(
        self,
    ) -> None:
        brief = {
            "schema_version": 5,
            "character_style_targets": {
                "犬夜叉": "child-form",
                "十六夜": "default-form",
                "杀生丸": "default-form",
            },
        }
        manifest = {
            "references": [
                {
                    "role": "style",
                    "style_scope": "character",
                    "subject_forms": {"犬夜叉": ["child-form"]},
                }
            ]
        }
        assignments = character_style_assignments(brief, manifest)
        self.assertEqual(
            assignments["犬夜叉=child-form"]["tier"], "exact-character-form"
        )
        self.assertEqual(
            assignments["十六夜=default-form"]["tier"],
            "missing-exact-character-form",
        )
        self.assertEqual(assignments["杀生丸=default-form"]["inputs"], [])
        self.assertEqual(
            character_style_coverage_failures(brief, manifest),
            [
                "missing selected-medium character-style evidence: 十六夜=default-form",
                "missing selected-medium character-style evidence: 杀生丸=default-form",
            ],
        )
        manifest["references"].append(
            {
                "role": "style",
                "style_scope": "character",
                "subject_forms": {"十六夜": ["default-form"]},
            }
        )
        assignments = character_style_assignments(brief, manifest)
        self.assertEqual(
            assignments["十六夜=default-form"]["tier"], "exact-character-form"
        )

    def test_current_character_style_entry_rejects_unrequested_cocharacter(
        self,
    ) -> None:
        targets = {"犬夜叉": "human-form"}
        entry = {
            "role": "style",
            "style_scope": "character",
            "subjects": ["犬夜叉", "戈薇"],
            "subject_forms": {
                "犬夜叉": ["human-form"],
                "戈薇": ["default-form"],
            },
        }
        self.assertFalse(strict_character_style_entry(entry, targets))
        failures = character_style_coverage_failures(
            {"schema_version": 5, "character_style_targets": targets},
            {"references": [entry]},
        )
        self.assertIn(
            "ineligible character-style evidence at Input 1: contains an unrequested character or wrong form",
            failures,
        )
        for unrequested_subject in ("和尚", "普通人物"):
            with self.subTest(unrequested_subject=unrequested_subject):
                self.assertFalse(
                    strict_character_style_entry(
                        {
                            "subjects": ["犬夜叉", unrequested_subject],
                            "subject_forms": {
                                "犬夜叉": ["human-form"],
                                unrequested_subject: ["default-form"],
                            },
                        },
                        targets,
                    )
                )

    def test_medium_shot_prompt_maps_each_character_without_sample_blacklist(
        self,
    ) -> None:
        brief = self.brief("new")
        brief["shot"] = "medium-shot"
        brief["character_style_targets"] = {
            "犬夜叉": "child-form",
            "十六夜": "default-form",
        }
        manifest = {
            "references": [
                {
                    "role": "style",
                    "style_scope": "character",
                    "subject_forms": {"犬夜叉": ["child-form"]},
                    "instructions": "child style",
                },
                {
                    "role": "style",
                    "style_scope": "character",
                    "subject_forms": {"十六夜": ["default-form"]},
                    "instructions": "Izayoi style",
                },
            ]
        }
        prompt = compile_prompt(brief, manifest)
        self.assertIn("Per-character rendering map", prompt)
        self.assertIn("犬夜叉=child-form: Input 1 (exact)", prompt)
        self.assertIn("十六夜=default-form: Input 2 (exact)", prompt)
        self.assertIn("Manga finish calibration", prompt)
        self.assertIn("Monochrome output or screen tone alone is insufficient", prompt)
        self.assertNotIn("continuous shine bands", prompt)
        self.assertNotIn("wet reflections", prompt)

    def test_tv_character_mapping_is_selected_medium_neutral(self) -> None:
        brief = self.brief("new")
        brief["medium"] = "tv"
        brief["character_style_targets"] = {"犬夜叉": "half-demon-form"}
        manifest = {
            "references": [
                {
                    "role": "style",
                    "style_scope": "character",
                    "subject_forms": {"犬夜叉": ["half-demon-form"]},
                    "instructions": "TV character rendering only",
                }
            ]
        }
        prompt = compile_prompt(brief, manifest)
        self.assertIn("selected-medium contours", prompt)
        self.assertNotIn("serialized-manga contour", prompt)
        self.assertNotIn("Manga finish calibration", prompt)

    def test_manga_candidate_components_allow_evidence_backed_na_at_any_shot(
        self,
    ) -> None:
        self.assertTrue(
            requires_manga_medium_components(
                {
                    "medium": "manga",
                    "shot": "wide-shot",
                    "character_style_targets": {"犬夜叉": "half-demon-form"},
                }
            )
        )
        self.assertTrue(
            requires_manga_medium_components(
                {
                    "medium": "manga",
                    "shot": "close-up",
                    "character_style_targets": {"犬夜叉": "human-form"},
                }
            )
        )
        checks = [
            parse_medium_component_check(
                f"{component}=pass:visible evidence for {component}"
            )
            for component in (
                "face-hair",
                "fabric-fold",
                "scene-material",
                "value-hierarchy",
            )
        ]
        self.assertEqual(
            medium_component_failures("candidate", checks, required=True), []
        )
        checks[2] = parse_medium_component_check(
            "scene-material=warning:local foreground texture is dense but subordinate"
        )
        self.assertEqual(
            medium_component_failures("candidate", checks, required=True), []
        )
        checks[0] = parse_medium_component_check(
            "face-hair=n/a:characters are too small to inspect in this wide shot"
        )
        checks[1] = parse_medium_component_check(
            "fabric-fold=n/a:garment folds are below readable scale"
        )
        self.assertEqual(
            medium_component_failures("candidate", checks, required=True), []
        )
        self.assertIn(
            "missing manga medium components: scene-material, value-hierarchy",
            medium_component_failures("candidate", checks[:2], required=True),
        )
        failed = list(checks)
        failed[0] = parse_medium_component_check(
            "face-hair=fail:hair has a continuous glossy highlight band"
        )
        self.assertIn(
            "failed manga medium components: face-hair",
            medium_component_failures("candidate", failed, required=True),
        )
        failed[-1] = parse_medium_component_check(
            "value-hierarchy=n/a:image is monochrome"
        )
        self.assertIn(
            "value-hierarchy cannot be n/a for a manga candidate",
            medium_component_failures("candidate", failed, required=True),
        )

    def test_candidate_acceptance_is_not_counted_as_a_second_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "tasks" / "candidate-acceptance"
            task.mkdir(parents=True)
            (task / "brief.json").write_text(
                json.dumps(
                    {
                        "medium": "manga",
                        "intent": "new",
                        "created_at": "2026-08-17T10:00:00+08:00",
                    }
                ),
                encoding="utf-8",
            )
            (task / "reference-manifest.json").write_text(
                json.dumps({"references": []}), encoding="utf-8"
            )
            (task / "prompt.md").write_text("compiled prompt", encoding="utf-8")
            generated = task / "candidate.png"
            generated.write_bytes(b"same generated image")
            preview_checks = [
                "identity=pass:identity matches",
                "request=pass:request matches",
                "medium=pass:medium matches",
                "technical=pass:image is complete",
            ]
            candidate_args = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "candidate",
                "--output",
                str(generated),
                "--duration-seconds",
                "10",
            ]
            for check in preview_checks:
                candidate_args.extend(("--preview-check", check))
            with patch("sys.argv", candidate_args), redirect_stdout(io.StringIO()):
                self.assertEqual(record_attempt_main(), 0)
            accepted_args = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "accepted",
                "--output",
                str(generated),
            ]
            with patch("sys.argv", accepted_args), redirect_stdout(io.StringIO()):
                self.assertEqual(record_attempt_main(), 0)
            accepted = json.loads(
                (task / "attempts" / "002" / "attempt.json").read_text(encoding="utf-8")
            )
            result = json.loads((task / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(accepted["accepted_from_attempt"], 1)
            self.assertFalse(accepted["counts_as_generation"])
            self.assertFalse(result["revision_required"])
            report_output = io.StringIO()
            with (
                patch(
                    "sys.argv",
                    [
                        "reference_feedback_report.py",
                        "--workflow-root",
                        str(root),
                        "--json",
                    ],
                ),
                redirect_stdout(report_output),
            ):
                self.assertEqual(reference_feedback_report_main(), 0)
            report = json.loads(report_output.getvalue())
            self.assertEqual(
                report["generation_transport"]["by_semantic_intent"]["new"]["attempts"],
                1,
            )
            self.assertEqual(report["response_slo"]["eligible_previews"], 1)

    def test_candidate_rejection_is_not_counted_as_a_second_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "tasks" / "candidate-rejection"
            task.mkdir(parents=True)
            (task / "brief.json").write_text(
                json.dumps(
                    {
                        "medium": "manga",
                        "intent": "new",
                        "created_at": "2026-08-17T10:00:00+08:00",
                    }
                ),
                encoding="utf-8",
            )
            (task / "reference-manifest.json").write_text(
                json.dumps({"references": []}), encoding="utf-8"
            )
            (task / "prompt.md").write_text("compiled prompt", encoding="utf-8")
            generated = task / "candidate.png"
            generated.write_bytes(b"same generated image")
            candidate_args = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "candidate",
                "--output",
                str(generated),
            ]
            for check in (
                "identity=pass:identity matches",
                "request=pass:request matches",
                "medium=pass:medium matches",
                "technical=pass:image is complete",
            ):
                candidate_args.extend(("--preview-check", check))
            with patch("sys.argv", candidate_args), redirect_stdout(io.StringIO()):
                self.assertEqual(record_attempt_main(), 0)
            rejected_args = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "rejected",
                "--output",
                str(generated),
                "--failure",
                "medium=character finish is too polished",
                "--feedback",
                "explicit user rejection",
            ]
            with patch("sys.argv", rejected_args), redirect_stdout(io.StringIO()):
                self.assertEqual(record_attempt_main(), 0)
            rejected = json.loads(
                (task / "attempts" / "002" / "attempt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(rejected["decision_from_attempt"], 1)
            self.assertEqual(rejected["rejected_from_attempt"], 1)
            self.assertFalse(rejected["counts_as_generation"])
            report_output = io.StringIO()
            with (
                patch(
                    "sys.argv",
                    [
                        "reference_feedback_report.py",
                        "--workflow-root",
                        str(root),
                        "--json",
                    ],
                ),
                redirect_stdout(report_output),
            ):
                self.assertEqual(reference_feedback_report_main(), 0)
            report = json.loads(report_output.getvalue())
            self.assertEqual(
                report["generation_transport"]["by_semantic_intent"]["new"]["attempts"],
                1,
            )
            self.assertEqual(report["response_slo"]["eligible_previews"], 1)

    def test_character_only_medium_shot_does_not_invent_scene_economy(self) -> None:
        traits = retrieval_traits_for(
            "犬夜叉正面半身肖像",
            "medium-shot",
            medium="manga",
        )
        self.assertNotIn("scene-economy:authored-negative-space", traits)

    def test_scene_economy_is_a_weak_boost_below_exact_action(self) -> None:
        base = {
            "filename_terms": [],
            "subjects": [],
            "subject_forms": {},
            "folder_tags": [],
            "content_label": "",
            "relative_path": "",
            "note": "",
            "eligible_roles": ["rendering"],
            "shot_types": ["wide-shot"],
        }
        terms = [
            "action:swing-weapon",
            "scene-economy:authored-negative-space",
            "detail-falloff:strong",
        ]
        economy_score, _ = retrieval_relevance(
            {
                **base,
                "tags": [
                    "scene-economy:authored-negative-space",
                    "detail-falloff:strong",
                ],
            },
            query_terms=terms,
            shots=["wide-shot"],
            role="rendering",
        )
        action_score, _ = retrieval_relevance(
            {**base, "tags": ["action:swing-weapon"]},
            query_terms=terms,
            shots=["wide-shot"],
            role="rendering",
        )
        self.assertGreater(action_score, economy_score)

    def test_environment_scene_style_requires_positive_economy_tags(self) -> None:
        brief = {
            "retrieval_traits": [
                "background:night",
                "effect-type:rain",
                "scene-economy:authored-negative-space",
                "detail-falloff:strong",
            ]
        }
        dense_scene = {
            "item_id": "manga-curated:file:dense-rain",
            "reference_domain": "scene",
            "tags": json.dumps(["background:night", "effect-type:rain"]),
        }
        economical_scene = {
            **dense_scene,
            "item_id": "manga-curated:file:economical-scene",
            "tags": json.dumps(
                [
                    "scene-economy:authored-negative-space",
                    "detail-falloff:strong",
                ]
            ),
        }
        self.assertEqual(
            len(
                scene_economy_reference_failures(brief, dense_scene, {"role": "style"})
            ),
            1,
        )
        self.assertEqual(
            scene_economy_reference_failures(
                brief, economical_scene, {"role": "style"}
            ),
            [],
        )
        self.assertEqual(
            len(
                scene_economy_reference_failures(
                    brief,
                    dense_scene,
                    {
                        "role": "content",
                        "content_kind": "scene",
                        "scene_style_coverage": "HIT",
                    },
                )
            ),
            1,
        )

    def test_prop_qa_uses_ledger_topology_without_failure_examples(self) -> None:
        checks = qa_items(
            "manga",
            "new",
            shot="action",
            prop_forms={"铁碎牙": "transformed-form"},
        )
        text = "\n".join(check for _, check in checks)
        self.assertIn("单一连续宽刃", text)
        self.assertIn("刀身×1", text)
        self.assertNotIn("两根并行獠牙", text)

    def test_planner_forwards_explicit_shot_to_initializer(self) -> None:
        source = (SCRIPTS / "plan_art_task.py").read_text(encoding="utf-8")
        initializer = source.split("command = [", 1)[1].split("completed =", 1)[0]
        self.assertIn('command.extend(["--shot", args.shot])', initializer)
        self.assertIn('"--prefer-subject-form"', source)

    def test_planner_infers_profile_and_routes_it_to_identity_and_style(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "plan_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "kagome-profile-routing",
                "--request",
                "戈薇侧身站立，双手托住大型纸灯笼",
                "--identity-form",
                "戈薇=default-form",
                "--shot",
                "upper-body",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(plan_art_task_main(), 0)
            result = json.loads(output.getvalue())
            task_dir = Path(result["task_dir"])
            plan = json.loads(
                Path(result["retrieval_plan"]).read_text(encoding="utf-8")
            )
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["schema_version"], 5)
            self.assertEqual(plan["view_angle"], "profile")
            self.assertEqual(
                plan["character_style_fallbacks"],
                [],
            )
            self.assertEqual(brief["view_angle"], "profile")
            prompt = (task_dir / "prompt.md").read_text(encoding="utf-8")
            self.assertIn("额头到短而克制的鼻尖", prompt)
            identity = plan["layers"][0]
            primary = identity["primary_commands"][0]
            self.assertEqual(primary[primary.index("--shot") + 1], "upper-body")
            self.assertEqual(primary[primary.index("--view-angle") + 1], "profile")
            viewless = identity["fallback_without_view_angle"][0]
            self.assertNotIn("--view-angle", viewless)
            character_style = plan["layers"][1]["primary_commands"][0]
            self.assertEqual(
                character_style[character_style.index("--view-angle") + 1],
                "profile",
            )
            self.assertIn("--intent-text", character_style)
            preferred_pairs = [
                character_style[index + 1]
                for index, value in enumerate(character_style)
                if value == "--prefer-subject-form"
            ]
            self.assertEqual(
                preferred_pairs,
                ["戈薇=default-form"],
            )
            selection_budget = plan["layers"][1]["selection_budget"]
            self.assertIn("exact requested forms", selection_budget)
            self.assertIn("ineligible before ranking", selection_budget)
            self.assertNotIn("ranking preferences, not eligibility gates", selection_budget)
            self.assertNotIn("compatible same-view subject", selection_budget)

    def test_manga_edit_preserves_two_sided_finish_band(self) -> None:
        prompt = compile_prompt(self.brief("edit"), {"references": []})
        self.assertIn("Do not drift toward extra", prompt)
        self.assertIn("digital polish", prompt)
        self.assertIn("strip away identity-critical", prompt)

    def test_target_only_edit_does_not_invent_style_references(self) -> None:
        prompt = compile_prompt(
            self.brief("edit"),
            {
                "references": [
                    {
                        "role": "target",
                        "item_id": "target",
                        "instructions": "Preserve the target.",
                    }
                ]
            },
        )
        self.assertIn("Target-only manga preservation", prompt)
        self.assertIn("no external style reference is attached", prompt)
        self.assertNotIn("selected character and scene references control", prompt)
        self.assertNotIn("reference-matched marks", prompt)

    def test_single_style_domain_calibration_names_only_attached_authority(
        self,
    ) -> None:
        brief = self.brief("edit")
        character_prompt = compile_prompt(
            brief,
            {
                "references": [
                    {"role": "target", "item_id": "target"},
                    {
                        "role": "style",
                        "item_id": "character-style",
                        "style_scope": "character",
                    },
                ]
            },
        )
        self.assertIn("Character-reference manga calibration", character_prompt)
        self.assertNotIn(
            "selected character and scene references control", character_prompt
        )

    def test_manga_illustration_is_compiled_as_serialized_panel_for_any_shot(
        self,
    ) -> None:
        brief = self.brief("new")
        brief["shot"] = "medium-shot"
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("single borderless serialized-manga panel", prompt)
        self.assertIn("not a standalone illustration", prompt)
        self.assertNotIn("; illustration;", prompt)

    def test_scene_economy_prompt_keeps_scene_density_off_character(self) -> None:
        brief = self.brief("new")
        brief["shot"] = "medium-shot"
        brief["retrieval_traits"] = [
            "background:night",
            "effect-type:rain",
            "scene-economy:authored-negative-space",
            "detail-falloff:strong",
        ]
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("Scene-density ceiling", prompt)
        self.assertIn("Never transfer the scene reference's texture frequency", prompt)
        self.assertIn("only the character-style anchor", prompt)

    def test_manga_medium_edit_requires_actual_simplification(self) -> None:
        brief = self.brief("edit")
        brief["change_category"] = "medium"
        brief["change_scope"] = "scene"
        brief["change_request"] = "改成简练的连载漫画画法"
        brief["invariants"] = []
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("Scene-rendering replacement is the named edit", prompt)
        self.assertIn("environmental materials, water, rocks", prompt)
        self.assertIn("existing garment", prompt)
        self.assertIn("value hierarchy exactly from the target", prompt)
        self.assertIn("Do not remove character strands or folds", prompt)
        self.assertIn("replace only the declared rendering domain", prompt)
        self.assertIn("Scene-scope manga calibration", prompt)
        self.assertNotIn("selected character and scene references control", prompt)

    def test_character_tone_edit_uses_character_style_for_garment_values_only(
        self,
    ) -> None:
        brief = self.brief("edit")
        brief["change_category"] = "tone"
        brief["change_scope"] = "character"
        brief["change_request"] = "恢复犬夜叉深色衣服的网点层级"
        brief["dominant_scene_materials"] = ["溪水", "岩石"]
        brief["retrieval_traits"] = [
            "scene-economy:authored-negative-space",
            "detail-falloff:strong",
        ]
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("Character-rendering replacement is the named edit", prompt)
        self.assertIn("fabric and fold treatment", prompt)
        self.assertIn("halftone hierarchy", prompt)
        self.assertIn("Preserve official costume construction", prompt)
        self.assertIn("preserve the target's scene materials", prompt)
        self.assertIn("Character-scope manga calibration", prompt)
        self.assertNotIn("Scene-material scope", prompt)
        self.assertNotIn("Scene-density ceiling", prompt)
        self.assertNotIn("selected character and scene references control", prompt)

    def test_scoped_style_validation_rejects_scene_reference_for_character_tone(
        self,
    ) -> None:
        brief = self.brief("edit")
        brief["change_category"] = "tone"
        brief["change_scope"] = "character"
        manifest = {
            "references": [
                {"role": "target", "item_id": "target"},
                {
                    "role": "style",
                    "item_id": "creek-scene",
                    "style_scope": "scene",
                    "reference_domain": "scene",
                },
            ]
        }
        failures = scoped_style_failures(brief, manifest, require_scope=True)
        self.assertEqual(len(failures), 1)
        self.assertIn("requires one character-style reference", failures[0])

    def test_scoped_style_validation_requires_scope_before_generation(self) -> None:
        brief = self.brief("microfix")
        brief["change_category"] = "medium"
        manifest = {
            "references": [
                {"role": "target", "item_id": "target"},
                {
                    "role": "style",
                    "item_id": "creek-scene",
                    "style_scope": "scene",
                },
            ]
        }
        failures = scoped_style_failures(brief, manifest, require_scope=True)
        self.assertTrue(any("brief.change_scope" in failure for failure in failures))
        self.assertEqual(
            scoped_style_failures(brief, manifest, require_scope=False), []
        )
        brief["change_scope_schema_version"] = CHANGE_SCOPE_SCHEMA_VERSION
        current_failures = scoped_style_failures(brief, manifest, require_scope=False)
        self.assertTrue(
            any("brief.change_scope" in failure for failure in current_failures)
        )

    def test_scope_contract_version_requires_exact_integer(self) -> None:
        brief = self.brief("edit")
        brief["change_category"] = "tone"
        brief["change_scope"] = "character"
        manifest = {
            "references": [
                {
                    "role": "style",
                    "item_id": "character-style",
                    "style_scope": "character",
                }
            ]
        }
        for invalid in (True, 1.0, "1"):
            brief["change_scope_schema_version"] = invalid
            failures = scoped_style_failures(brief, manifest, require_scope=False)
            self.assertTrue(
                any("change_scope_schema_version" in failure for failure in failures),
                repr(invalid),
            )

    def test_legacy_scoped_validation_uses_catalog_domain(self) -> None:
        brief = self.brief("edit")
        brief["change_category"] = "medium"
        brief["change_scope"] = "character"
        manifest = {
            "references": [{"role": "style", "item_id": "legacy-character-style"}]
        }
        self.assertEqual(
            scoped_style_failures(
                brief,
                manifest,
                require_scope=False,
                catalog_reference_domains={"legacy-character-style": "character-style"},
            ),
            [],
        )

    def test_scoped_style_qa_locks_untouched_domain(self) -> None:
        scene_checks = qa_items("manga", "edit", "medium", "scene")
        character_checks = qa_items("manga", "edit", "tone", "character")
        self.assertTrue(
            any(
                category == "preservation" and "既有服装" in check
                for category, check in scene_checks
            )
        )
        self.assertTrue(
            any(
                category == "medium" and "场景材质" in check
                for category, check in character_checks
            )
        )
        microfix_scene_checks = qa_items("manga", "microfix", "tone", "scene")
        microfix_character_checks = qa_items("manga", "microfix", "tone", "character")
        self.assertTrue(
            any("scene-style" in check for _, check in microfix_scene_checks)
        )
        self.assertTrue(
            any("character-style" in check for _, check in microfix_character_checks)
        )

    def test_wide_manga_medium_edit_locks_target_staging(self) -> None:
        brief = self.brief("edit")
        brief["shot"] = "wide-shot"
        brief["change_category"] = "medium"
        brief["change_scope"] = "scene"
        brief["change_request"] = "继续贴近原作漫画的场景画法"
        brief["invariants"] = []
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("Wide-shot preservation lock", prompt)
        self.assertIn("character scale and placement", prompt)
        self.assertIn("overall black-white distribution", prompt)
        self.assertIn("Do not enlarge the character", prompt)
        self.assertIn("recrop or recompose the scene", prompt)
        self.assertIn("Economy is not uniform simplification", prompt)
        self.assertIn("Correct the finish locally", prompt)

    def test_wide_manga_edit_qa_rejects_dramatic_reauthoring(self) -> None:
        checks = qa_items("manga", "edit", "medium", shot="wide-shot")
        self.assertTrue(
            any(
                category == "preservation"
                and "人物尺度与位置" in check
                and "增加大块重黑" in check
                for category, check in checks
            )
        )
        self.assertTrue(
            any(
                category == "medium" and "全画面均匀变空" in check
                for category, check in checks
            )
        )

    def test_manga_medium_edit_qa_rejects_tone_only_conversion(self) -> None:
        checks = qa_items("manga", "edit", "medium")
        self.assertTrue(
            any(
                category == "medium" and "不只是去掉灰阶" in check
                for category, check in checks
            )
        )

    def test_runtime_contract_does_not_pin_a_manga_volume_or_page(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        runtime_contracts = [
            skill_root / "SKILL.md",
            skill_root / "references" / "workflow-contract.md",
        ]
        for path in runtime_contracts:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Volume 13", text)
            self.assertNotIn("Volume-13", text)

    def test_rendering_layer_result_can_be_read_without_fixed_style_input(self) -> None:
        evidence = """## Layer 1: official identity
- Result: `HIT`
## Layer 2: Manga or TV screenshots
- Result: `INSUFFICIENT`
## Layer 3: exact content evidence
- Selected-medium result: `SKIP`
"""
        section = evidence.split("## Layer 2:", 1)[-1].split("## Layer 3:", 1)[0]
        self.assertEqual(retrieval_result(section, "Result"), "INSUFFICIENT")

    def test_rendering_coverage_gate_requires_focus_and_all_five_hits(self) -> None:
        evidence = """- Character mark-making coverage: HIT
- Hair and face linework coverage: HIT
- Fabric and fold treatment coverage: HIT
- Garment value hierarchy coverage:
- Scene rendering coverage: HIT
"""
        failures = rendering_coverage_failures(
            evidence,
            [
                {
                    "role": "style",
                    "item_id": "manga-curated:file:test",
                    "focus": "",
                    "instructions": "Control manga mark-making only.",
                }
            ],
            1,
            "manga",
        )
        self.assertTrue(any("Garment value hierarchy" in item for item in failures))
        self.assertTrue(any("no exact rendering focus" in item for item in failures))
        self.assertTrue(
            any("authority instruction is incomplete" in item for item in failures)
        )

    def test_scene_material_scope_allows_second_core_style_anchor(self) -> None:
        instruction = instruction_for(
            "style",
            "manga",
            focus="树干树皮与聚类树叶",
            source_medium="manga",
        )
        evidence = """- Character mark-making coverage: HIT
- Hair and face linework coverage: HIT
- Fabric and fold treatment coverage: HIT
- Garment value hierarchy coverage: HIT
- Scene rendering coverage: HIT
- Dominant material rendering coverage: HIT — 树干树皮与聚类树叶
"""
        failures = rendering_coverage_failures(
            evidence,
            [
                {
                    "role": "style",
                    "item_id": "manga-curated:file:test",
                    "focus": "树干树皮与聚类树叶",
                    "instructions": instruction,
                }
            ],
            2,
            "manga",
            ["树干树皮与聚类树叶", "石阶石灯笼与岩石表面"],
        )
        self.assertFalse(any("one primary style anchor" in item for item in failures))
        self.assertFalse(any("石阶石灯笼与岩石表面" in item for item in failures))

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
                "status": "candidate",
                "output": str(output.resolve()),
                "output_sha256": digest,
            }
            (attempt_dir / "attempt.json").write_text(
                json.dumps(
                    {
                        "attempt": 1,
                        "status": "candidate",
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

    def test_new_manga_qa_grades_finish_drift_by_severity(self) -> None:
        checks = qa_items("manga", "new")
        self.assertTrue(
            any(
                category == "medium"
                and "局部细节较多" in check
                and "warning" in check
                and "精修黑白插画" in check
                for category, check in checks
            )
        )
        self.assertTrue(
            any(
                category == "medium"
                and "通用动漫脸" in check
                and "空洞场景" in check
                and "身份关键" in check
                for category, check in checks
            )
        )

    def test_finish_severity_is_conditioned_for_three_scene_types(self) -> None:
        wide_checks = qa_items("manga", "new", shot="wide-shot")
        self.assertTrue(
            any(
                category == "medium"
                and "单一从属区域略密" in check
                and "多个材质或远近层" in check
                and "透视正确" in check
                and "不能记 warning" in check
                and "warning" in check
                for category, check in wide_checks
            )
        )
        character_checks = qa_items("manga", "new", shot="medium-shot")
        self.assertTrue(
            any(
                category == "medium"
                and "人物中近景" in check
                and "跨区域均匀光泽" in check
                and "warning" in check
                for category, check in character_checks
            )
        )
        weather_checks = qa_items("manga", "new", shot="action")
        self.assertTrue(
            any(
                category == "medium"
                and "雨线、反光、阴影" in check
                and "电影式照明" in check
                and "warning" in check
                for category, check in weather_checks
            )
        )

    def test_manga_microfix_qa_preserves_finish_level(self) -> None:
        checks = qa_items("manga", "microfix", "anatomy")
        self.assertTrue(
            any(
                category == "preservation"
                and "数字精修" in check
                and "身份关键线条" in check
                for category, check in checks
            )
        )

    def test_style_planning_does_not_filter_rendering_by_identity(self) -> None:
        plan_source = (SCRIPTS / "plan_art_task.py").read_text(encoding="utf-8")
        style_block = plan_source.split("style_base =", 1)[1].split("layers =", 1)[0]
        self.assertNotIn('"--subject"', style_block)
        self.assertNotIn('"--form"', style_block)

    def test_multi_character_plan_uses_one_ranked_style_search_with_all_preferences(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "plan_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "mother-child-character-style",
                "--request",
                "十六夜替幼年犬夜叉擦头发",
                "--identity-form",
                "犬夜叉=child-form",
                "--identity-form",
                "十六夜=default-form",
                "--shot",
                "medium-shot",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(plan_art_task_main(), 0)
            result = json.loads(output.getvalue())
            task_dir = Path(result["task_dir"])
            brief = json.loads((task_dir / "brief.json").read_text(encoding="utf-8"))
            evidence = (task_dir / "evidence-log.md").read_text(encoding="utf-8")
            plan = json.loads(
                Path(result["retrieval_plan"]).read_text(encoding="utf-8")
            )
            style_layer = next(layer for layer in plan["layers"] if layer["layer"] == 2)
            commands = style_layer["primary_commands"]
            self.assertEqual(len(commands), 1)
            self.assertIn("犬夜叉=child-form", commands[0])
            self.assertIn("十六夜=default-form", commands[0])
            self.assertEqual(
                brief["character_style_targets"],
                {"犬夜叉": "child-form", "十六夜": "default-form"},
            )
            self.assertIn("Character style preference 犬夜叉=child-form", evidence)
            self.assertIn("Character style preference 十六夜=default-form", evidence)
            self.assertIn(
                "one combined character-style candidate set",
                style_layer["selection_budget"],
            )
            self.assertIn(
                "unrequested known character or wrong form is ineligible",
                style_layer["selection_budget"],
            )
            self.assertIn(
                "never broaden to another character or form",
                style_layer["selection_budget"],
            )

    def test_new_task_planner_does_not_route_identity_cards(self) -> None:
        plan_source = (SCRIPTS / "plan_art_task.py").read_text(encoding="utf-8")
        self.assertNotIn("resolve_identity_card", plan_source)
        identity_block = plan_source.split("official_commands =", 1)[1].split(
            "style_source =", 1
        )[0]
        self.assertIn('"--source",\n            "official"', identity_block)
        self.assertNotIn('"--identity-card"', identity_block)

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

    def test_preference_profile_uses_only_repeated_accepted_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "tasks" / "accepted-style"
            task.mkdir(parents=True)
            (task / "brief.json").write_text(
                json.dumps({"medium": "manga"}), encoding="utf-8"
            )
            events = [
                {"status": "accepted", "tags": ["selective-detail"]},
                {"status": "accepted", "tags": ["selective-detail"]},
                {"status": "rejected", "tags": ["selective-detail", "failed-case"]},
            ]
            (task / "preference-events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in events) + "\n",
                encoding="utf-8",
            )
            output = write_profile(root)
            profile = json.loads(output.read_text(encoding="utf-8"))
            traits = {row["tag"]: row["count"] for row in profile["manga"]["traits"]}
            self.assertEqual(traits, {"selective-detail": 2})
            self.assertEqual(profile["minimum_support"], 2)

    def test_acceptance_survives_derived_preference_refresh_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "tasks" / "accepted-task"
            task.mkdir(parents=True)
            created_at = "2026-08-16T12:00:00+08:00"
            (task / "brief.json").write_text(
                json.dumps(
                    {
                        "medium": "manga",
                        "intent": "new",
                        "created_at": created_at,
                    }
                ),
                encoding="utf-8",
            )
            (task / "reference-manifest.json").write_text(
                json.dumps({"references": []}), encoding="utf-8"
            )
            (task / "prompt.md").write_text("compiled prompt", encoding="utf-8")
            generated = task / "accepted.png"
            generated.write_bytes(b"accepted image")
            arguments = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "accepted",
                "--output",
                str(generated),
                "--json",
            ]
            output = io.StringIO()
            with (
                patch("sys.argv", arguments),
                patch(
                    "record_attempt.write_profile",
                    side_effect=ValueError("broken preference event"),
                ),
                redirect_stdout(output),
            ):
                self.assertEqual(record_attempt_main(), 0)
            payload = json.loads(output.getvalue())
            result = json.loads((task / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "accepted")
            self.assertTrue((task / "attempts" / "001" / "attempt.json").is_file())
            self.assertIn(
                "broken preference event", payload["preference_profile_warning"]
            )

    def test_split_domain_acceptance_is_blocked_before_attempt_when_qa_is_pending(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "tasks" / "pending-qa-task"
            task.mkdir(parents=True)
            (task / "brief.json").write_text(
                json.dumps(
                    {
                        "medium": "manga",
                        "intent": "new",
                        "created_at": "2026-08-16T12:00:00+08:00",
                        "style_strategy": "manga-character-style-canonical-scene",
                    }
                ),
                encoding="utf-8",
            )
            (task / "reference-manifest.json").write_text(
                json.dumps({"references": []}), encoding="utf-8"
            )
            (task / "prompt.md").write_text("compiled prompt", encoding="utf-8")
            (task / "qa.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "dimensions": [
                            {"id": dimension_id, "status": "pending", "note": ""}
                            for dimension_id in (
                                "character_identity",
                                "character_style",
                                "scene_identity",
                                "scene_style",
                                "action_request",
                                "composition_integration",
                            )
                        ],
                        "checks": [
                            {"check": "技术完整", "status": "pending", "note": ""}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            generated = task / "candidate.png"
            generated.write_bytes(b"candidate")
            arguments = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "accepted",
                "--output",
                str(generated),
            ]
            with patch("sys.argv", arguments), self.assertRaises(SystemExit):
                record_attempt_main()
            self.assertFalse((task / "attempts" / "001").exists())
            self.assertFalse((task / "result.json").exists())

    def test_generic_new_task_cannot_accept_pending_six_dimension_qa(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "init_art_task.py",
                "--workflow-root",
                directory,
                "--slug",
                "generic-scene-pending-qa",
                "--medium",
                "manga",
                "--request",
                "人类形态犬夜叉在普通雨夜屋檐下守候",
                "--identity-form",
                "犬夜叉=human-form",
            ]
            output = io.StringIO()
            with patch("sys.argv", arguments), redirect_stdout(output):
                self.assertEqual(init_art_task_main(), 0)
            task = Path(output.getvalue().strip().splitlines()[-1])
            brief = json.loads((task / "brief.json").read_text(encoding="utf-8"))
            qa = json.loads((task / "qa.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["style_strategy"], "two-layer-manga-fast")
            self.assertTrue(is_split_domain_task(brief, qa))
            generated = task / "candidate.png"
            generated.write_bytes(b"candidate")
            record_arguments = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "accepted",
                "--output",
                str(generated),
            ]
            with patch("sys.argv", record_arguments), self.assertRaises(SystemExit):
                record_attempt_main()
            self.assertFalse((task / "attempts" / "001").exists())
            self.assertFalse((task / "result.json").exists())

    def test_identity_ledger_validator_checks_topology_and_inference(self) -> None:
        ledger = {
            "schema_version": 1,
            "characters": {
                "犬夜叉": {
                    "common": [],
                    "forms": {"half-demon-form": []},
                    "exclusions": [],
                },
                "测试刀": {
                    "kind": "prop",
                    "common": [],
                    "forms": {
                        "transformed-form": {
                            "features": ["宽刃"],
                            "topology": {
                                "connected_sequence": ["刀柄", "刀身", "刀尖"],
                                "counts": {"刀身": 1, "刀尖": 1},
                            },
                        }
                    },
                    "form_inference": {
                        "transformed-form": {
                            "explicit": ["变化后"],
                            "context": ["挥动"],
                        }
                    },
                    "exclusions": [],
                },
            },
        }
        self.assertEqual(identity_ledger_failures(ledger), [])
        ledger["characters"]["测试刀"]["forms"]["transformed-form"]["topology"][
            "counts"
        ]["刀尖"] = 0
        ledger["characters"]["测试刀"]["form_inference"]["missing-form"] = ["未知"]
        failures = identity_ledger_failures(ledger)
        self.assertTrue(any("positive integers" in failure for failure in failures))
        self.assertTrue(any("unknown form" in failure for failure in failures))

    def test_identity_ledger_validates_view_traits_and_rendering_fallbacks(
        self,
    ) -> None:
        ledger = {
            "schema_version": 1,
            "characters": {
                "犬夜叉": {
                    "common": [],
                    "forms": {"half-demon-form": []},
                    "view_traits": "broken",
                    "exclusions": [],
                },
                "戈薇": {
                    "common": [],
                    "forms": {"default-form": []},
                    "view_traits": {
                        "missing-form": {"profile": []},
                        "default-form": {
                            "sideways": ["侧脸"],
                            "profile": [],
                        },
                    },
                    "rendering_fallbacks": {
                        "profile": {
                            "不存在的人物": "default-form",
                            "犬夜叉": "not-a-form",
                        }
                    },
                    "exclusions": [],
                },
            },
        }
        failures = identity_ledger_failures(ledger)
        self.assertTrue(
            any("view_traits must be an object" in item for item in failures)
        )
        self.assertTrue(any("unknown view angle" in item for item in failures))
        self.assertTrue(any("at least one trait" in item for item in failures))
        self.assertTrue(any("unknown subject" in item for item in failures))
        self.assertTrue(any("unknown form not-a-form" in item for item in failures))

    def test_retrieval_benchmark_can_run_real_style_browser(self) -> None:
        case = {
            "id": "profile-browser",
            "tool": "browse_curated_styles",
            "intent_text": "戈薇侧身托住灯笼",
            "query": {
                "medium": "manga",
                "reference_domain": "character-style",
                "role": "rendering",
                "prefer_subject_form": [
                    "戈薇=default-form",
                    "珊瑚=default-form",
                ],
                "view_angle": "profile",
                "shot": ["upper-body"],
            },
            "relevant_item_ids": ["manga-curated:file:profile-sango"],
        }
        command = search_command(case, Path("/tmp/workflow"), 3)
        self.assertIn("browse_curated_styles.py", command[1])
        self.assertEqual(command.count("--prefer-subject-form"), 2)
        self.assertEqual(command[command.index("--view-angle") + 1], "profile")

    def test_retrieval_benchmark_requires_strict_character_style_pairs(self) -> None:
        dataset = {
            "schema_version": 1,
            "cases": [
                {
                    "id": "missing-strict-pair",
                    "intent_text": "人类形态犬夜叉独处",
                    "query": {
                        "source": "manga-curated",
                        "reference_domain": "character-style",
                        "role": "rendering",
                        "subject_form": ["犬夜叉=human-form"],
                    },
                    "relevant_item_ids": ["manga-curated:file:example"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "strict_subject_forms must exactly match",
            ):
                load_dataset(path)

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
