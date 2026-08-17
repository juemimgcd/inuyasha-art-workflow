from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

from benchmark_image_generation import (
    case_prompt,
    file_hash,
    json_hash,
    load_dataset,
    score_run,
    score_template,
)
from build_identity_cards import (
    build_cards,
    card_authority,
    load_recipes,
    parse_box,
    render_card,
    unmanaged_card_outputs,
)
from task_workflow import identity_requirements
from workflow_common import retrieval_traits_for


class IdentityCardTests(unittest.TestCase):
    def test_recipes_cover_supported_character_forms(self) -> None:
        recipes = load_recipes(SKILL_DIR / "references" / "identity-card-recipes.json")
        self.assertEqual(len(recipes["cards"]), 10)
        self.assertEqual(
            {
                card["form"]
                for card in recipes["cards"]
                if card["character"] == "犬夜叉"
            },
            {"half-demon-form", "human-form", "child-form"},
        )
        self.assertEqual(
            {
                card["form"]
                for card in recipes["cards"]
                if card["character"] == "戈薇"
            },
            {"default-form"},
        )
        self.assertEqual(
            {
                card["form"]
                for card in recipes["cards"]
                if card["character"] == "十六夜"
            },
            {"default-form"},
        )
        self.assertEqual(
            {
                card["form"]
                for card in recipes["cards"]
                if card["character"] == "弥勒"
            },
            {"default-form"},
        )
        self.assertEqual(
            {
                card["form"]
                for card in recipes["cards"]
                if card["character"] == "珊瑚"
            },
            {"demon-slayer-form", "battle-armor-form"},
        )
        tessaiga = [
            card for card in recipes["cards"] if card["character"] == "铁碎牙"
        ]
        self.assertEqual(
            {card["form"] for card in tessaiga},
            {"untransformed-form", "transformed-form"},
        )
        self.assertTrue(all(card["subject_kind"] == "prop" for card in tessaiga))
        self.assertEqual(
            len({(card["character"], card["form"]) for card in recipes["cards"]}),
            len(recipes["cards"]),
        )
        self.assertTrue(
            all(
                card["required_traits"] and card["excluded_traits"]
                for card in recipes["cards"]
            )
        )

    def test_box_parser_rejects_out_of_contract_values(self) -> None:
        self.assertEqual(parse_box([1, 2, 30, 40], "box"), (1, 2, 30, 40))
        with self.assertRaises(ValueError):
            parse_box([1, 2, 0, 40], "box")
        with self.assertRaises(ValueError):
            parse_box([1, 2, 3], "box")

    def test_identity_card_render_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (40, 30), "black").save(source)
            card = {"id": "test-card", "canvas": [100, 80]}
            panel = {
                "item_id": "official:test",
                "source_path": source,
                "target_box": [10, 10, 80, 60],
                "crop_box": None,
            }
            first = render_card(card, [panel])
            second = render_card(card, [panel])
            self.assertEqual(first, second)
            with Image.open(io.BytesIO(first)) as rendered:
                self.assertEqual(rendered.size, (100, 80))

    def test_card_authority_preserves_accepted_derivative_provenance(self) -> None:
        canonical = [{"source_authority": "canonical-identity"}]
        derived = [{"source_authority": "user-directed-derived-identity"}]
        self.assertEqual(
            card_authority(canonical),
            ("official-derived-transport-bundle", True, ["canonical-identity"]),
        )
        self.assertEqual(
            card_authority(derived),
            (
                "user-directed-derived-identity-transport-bundle",
                False,
                ["user-directed-derived-identity"],
            ),
        )

    def test_unmanaged_card_outputs_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "current.png").touch()
            stale = root / "stale.png"
            stale.touch()
            (root / "manifest.json").touch()
            self.assertEqual(
                unmanaged_card_outputs(root, {"current.png"}), [stale]
            )

    def test_build_mode_does_not_fail_on_outputs_it_will_supersede(self) -> None:
        source = (SKILL_DIR.parent.parent / "workflow" / "reference-workflow")
        if not (source / "catalog.sqlite3").is_file():
            self.skipTest("repository catalog is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            stale = output / "old-card.png"
            stale.touch()
            report = build_cards(
                SKILL_DIR / "references" / "identity-card-recipes.json",
                output,
                source / "catalog.sqlite3",
                check=False,
            )
            self.assertTrue(report["ok"])
            self.assertTrue(stale.is_file())


class GenerationBenchmarkTests(unittest.TestCase):
    def test_dataset_has_fixed_balanced_coverage(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        self.assertEqual(len(dataset["cases"]), 12)
        forms = [case["form"] for case in dataset["cases"]]
        self.assertEqual(forms.count("half-demon-form"), 4)
        self.assertEqual(forms.count("human-form"), 4)
        self.assertEqual(forms.count("child-form"), 4)
        self.assertTrue(
            {"close-up", "full-body", "back-view", "action", "two-shot"}
            <= {case["shot_type"] for case in dataset["cases"]}
        )

    def test_prompt_names_input_authority_without_catalog_hashes(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        case = next(
            value
            for value in dataset["cases"]
            if value["id"] == "human-form-kagome-two-shot"
        )
        prompt = case_prompt(dataset, case)
        self.assertIn("Input 1 (style)", prompt)
        self.assertIn("Input 2 (identity)", prompt)
        self.assertIn("Input 3 (identity for 戈薇)", prompt)
        self.assertNotIn("manga-curated:file", prompt)
        self.assertNotIn("official:file", prompt)

    def test_benchmark_checks_serialized_manga_economy(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        self.assertTrue(
            any(
                "90年代黑白连载漫画" in requirement
                and "现代精修插画" in requirement
                and "简陋线稿" in requirement
                for requirement in dataset["prompt_contract"]["global_requirements"]
            )
        )
        self.assertTrue(
            any(
                "身份关键" in requirement and "眼型" in requirement
                for requirement in dataset["prompt_contract"]["global_requirements"]
            )
        )
        representative = {
            case["shot_type"]: case["checks"]["manga_medium"]
            for case in dataset["cases"][:4]
            if case["shot_type"] in {"close-up", "full-body", "action"}
        }
        self.assertEqual(set(representative), {"close-up", "full-body", "action"})
        self.assertTrue(
            all(
                any("精修" in observation or "逐根发丝" in observation for observation in checks)
                for checks in representative.values()
            )
        )

    def test_izayoi_rain_two_shot_is_an_identity_and_density_regression(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        case = next(
            value
            for value in dataset["cases"]
            if value["id"] == "child-form-izayoi-two-shot"
        )
        self.assertIn("布巾", case["scene"])
        self.assertIn("湿透的长发", case["scene"])
        self.assertEqual(
            case["style_item_id"], "manga-curated:file:8f7a2ef700f3ecd25058"
        )
        identity = " ".join(case["checks"]["identity_features"])
        self.assertIn("细长平静眼型", identity)
        self.assertIn("厚齐刘海分束", identity)
        self.assertIn("收窄下颌", identity)
        medium = " ".join(case["checks"]["manga_medium"])
        self.assertIn("均匀精修", medium)
        self.assertIn("通用简陋线稿", medium)
        contact = " ".join(case["checks"]["anatomy_contact"])
        self.assertIn("双手、布巾、湿发与犬耳", contact)

    def test_profile_scene_uses_shared_human_profile_ledger(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        case = next(
            value
            for value in dataset["cases"]
            if value["id"] == "human-form-seated-profile"
        )
        traits = retrieval_traits_for(case["scene"], case["shot_type"])
        self.assertIn("view-angle:profile", traits)
        requirement = next(
            value
            for value in identity_requirements("犬夜叉", "human-form", traits)
            if "禁止女性化大圆眼" in value
        )
        self.assertIn("禁止女性化大圆眼", requirement)
        self.assertIn(requirement, case_prompt(dataset, case))

    def test_child_prompt_discloses_accepted_derivative_authority(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        case = next(
            value
            for value in dataset["cases"]
            if value["id"] == "child-form-front-full-body"
        )
        prompt = case_prompt(dataset, case)
        self.assertIn("用户明确要求制作", prompt)
        self.assertIn("不是出版社原始官方图", prompt)

    def test_score_template_requires_every_blocking_check(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        case = dataset["cases"][0]
        score = score_template(case)
        self.assertEqual(score["status"], "pending")
        self.assertEqual(set(score["checks"]), set(case["checks"]))
        self.assertTrue(all(value == "pending" for value in score["checks"].values()))

    def test_completed_single_case_run_reports_first_pass_metrics(self) -> None:
        dataset = load_dataset(SKILL_DIR / "references" / "generation-benchmark.json")
        dataset = {
            **dataset,
            "cases": [dataset["cases"][0]],
            "thresholds": {
                "minimum": {
                    "technical_success_rate": 1.0,
                    "first_pass_usable_rate": 1.0,
                    "identity_form_pass_rate": 1.0,
                    "identity_features_pass_rate": 1.0,
                    "costume_pass_rate": 1.0,
                    "manga_medium_pass_rate": 1.0,
                },
                "maximum": {
                    "median_generation_seconds": 10.0,
                    "p90_generation_seconds": 10.0,
                },
            },
        }
        case = dataset["cases"][0]
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            case_dir = run_dir / "cases" / case["id"]
            case_dir.mkdir(parents=True)
            inputs_dir = case_dir / "inputs"
            inputs_dir.mkdir()
            locked_input = inputs_dir / "01-style.png"
            Image.new("RGB", (16, 16), "black").save(locked_input)
            prompt = case_prompt(dataset, case)
            prompt_path = case_dir / "prompt.md"
            prompt_path.write_text(prompt, encoding="utf-8")
            inputs_path = case_dir / "inputs.json"
            inputs_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "case_id": case["id"],
                        "prompt_sha256": file_hash(prompt_path),
                        "input_order": [
                            {
                                "order": 1,
                                "role": "style",
                                "path": "inputs/01-style.png",
                                "sha256": file_hash(locked_input),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "dataset_id": dataset["id"],
                        "dataset_content_sha256": json_hash(dataset),
                        "backend": "test-backend",
                        "single_generation_per_case": True,
                        "case_ids": [case["id"]],
                        "case_locks": {
                            case["id"]: {
                                "prompt_sha256": file_hash(prompt_path),
                                "inputs_sha256": file_hash(inputs_path),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            output = case_dir / "output.png"
            Image.new("RGB", (16, 16), "white").save(output)
            score = score_template(case)
            score.update(
                {
                    "status": "usable",
                    "duration_seconds": 5.0,
                    "output": "output.png",
                    "output_sha256": file_hash(output),
                    "checks": {check_id: "pass" for check_id in case["checks"]},
                }
            )
            (case_dir / "score.json").write_text(
                json.dumps(score, ensure_ascii=False), encoding="utf-8"
            )
            report = score_run(dataset, run_dir)
            self.assertTrue(report["ok"])
            self.assertEqual(report["metrics"]["first_pass_usable_rate"], 1.0)
            self.assertEqual(report["metrics"]["median_generation_seconds"], 5.0)

            locked_input.write_bytes(b"changed")
            tampered = score_run(dataset, run_dir)
            self.assertFalse(tampered["ok"])
            self.assertTrue(
                any("invalid locked input" in failure for failure in tampered["failures"])
            )


if __name__ == "__main__":
    unittest.main()
