from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

from record_attempt import main as record_attempt_main
from visual_ab_eval import (
    assert_promoted,
    blind_run,
    effective_results,
    file_hash,
    judge_run,
    load_dataset,
    load_run,
    prepare_run,
    record_human_feedback,
    record_slot,
    results,
    validate_manifest,
)
from workflow_common import SHOT_VALUES

BACKEND = "same-image-backend"


class VisualAbEvalTests(unittest.TestCase):
    def dataset_path(self) -> Path:
        return SKILL_DIR / "references" / "visual-eval-v2.json"

    def dataset(self) -> dict:
        return load_dataset(self.dataset_path())

    def prepare_empty_run(self, root: Path, run_id: str) -> tuple[Path, dict]:
        dataset = self.dataset()
        run_dir = prepare_run(
            self.dataset_path(),
            root,
            run_id,
            "baseline-revision",
            "candidate-revision",
            BACKEND,
        )
        return run_dir, dataset

    def create_attempt(
        self,
        root: Path,
        case: dict,
        variant: str,
        *,
        generator: str = BACKEND,
        shot: str | None = None,
        extra_attempt: bool = False,
        reference_color: tuple[int, int, int] = (20, 30, 40),
    ) -> tuple[Path, Path]:
        task = root / "source-tasks" / f"{case['id']}-{variant}"
        task.mkdir(parents=True)
        brief = {
            "intent": case["intent"],
            "medium": case["medium"],
            "request": case["request"],
            "identity_forms": case["identity_forms"],
            "shot": shot or case["shot"],
            "aspect_ratio": case["aspect_ratio"],
        }
        prompt = f"locked prompt for {case['id']} {variant}\n"
        submitted = f"submitted prompt for {case['id']} {variant}\n"
        reference = task / "reference.png"
        Image.new("RGB", (12, 12), reference_color).save(reference)
        manifest = {
            "references": [
                {
                    "role": "style",
                    "item_id": f"style:{case['id']}",
                    "rendered_path": str(reference),
                    "content_hash": file_hash(reference),
                }
            ]
        }
        (task / "brief.json").write_text(
            json.dumps(brief, ensure_ascii=False), encoding="utf-8"
        )
        (task / "prompt.md").write_text(prompt, encoding="utf-8")
        (task / "reference-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        output = task / "output.png"
        color = (50, 80, 110) if variant == "baseline" else (90, 120, 150)
        Image.new("RGB", (16, 20), color).save(output)
        attempt_dir = task / "attempts" / "001"
        attempt_dir.mkdir(parents=True)
        snapshots = {
            "brief.json": json.dumps(brief, ensure_ascii=False),
            "prompt.md": prompt,
            "submitted-prompt.md": submitted,
            "reference-manifest.json": json.dumps(manifest),
        }
        for name, content in snapshots.items():
            (attempt_dir / name).write_text(content, encoding="utf-8")
        attempt = {
            "schema_version": 1,
            "attempt": 1,
            "status": "candidate",
            "generator": generator,
            "generation_seconds": 3.5,
            "output": str(output),
            "output_sha256": file_hash(output),
            "brief_sha256": file_hash(attempt_dir / "brief.json"),
            "compiled_prompt_sha256": file_hash(attempt_dir / "prompt.md"),
            "submitted_prompt_sha256": file_hash(
                attempt_dir / "submitted-prompt.md"
            ),
            "reference_manifest_sha256": file_hash(
                attempt_dir / "reference-manifest.json"
            ),
            "reference_item_ids": [f"style:{case['id']}"],
        }
        (attempt_dir / "attempt.json").write_text(
            json.dumps(attempt), encoding="utf-8"
        )
        if extra_attempt:
            second = task / "attempts" / "002"
            second.mkdir()
            (second / "attempt.json").write_text("{}", encoding="utf-8")
        return task, attempt_dir

    def prepare_recorded_run(
        self,
        root: Path,
        run_id: str,
        *,
        prepare_blind: bool = True,
    ) -> tuple[Path, dict]:
        run_dir, dataset = self.prepare_empty_run(root, run_id)
        for case in dataset["cases"]:
            for variant in ("baseline", "candidate"):
                task, attempt = self.create_attempt(root, case, variant)
                record_slot(run_dir, variant, case["id"], task, attempt)
        if prepare_blind:
            blind_run(run_dir)
        return run_dir, dataset

    def side_for(self, run_dir: Path, case_id: str, variant: str) -> str:
        key = json.loads(
            (run_dir / "blind" / "blind-key.json").read_text(encoding="utf-8")
        )
        return next(
            side
            for side, value in key["mapping"][case_id].items()
            if value["variant"] == variant
        )

    def test_dataset_is_exactly_three_cases_and_six_outputs(self) -> None:
        dataset = self.dataset()
        self.assertEqual(len(dataset["cases"]), 3)
        self.assertEqual(dataset["policy"]["cases_per_variant"], 3)
        self.assertEqual(dataset["policy"]["total_images"], 6)
        self.assertTrue(dataset["policy"]["single_generation_per_slot"])
        self.assertFalse(dataset["policy"]["automatic_retry"])
        self.assertTrue(all(case["shot"] in SHOT_VALUES for case in dataset["cases"]))
        wide_cases = [case for case in dataset["cases"] if case["shot"] == "wide-shot"]
        self.assertEqual(len(wide_cases), 1)
        self.assertTrue(
            any("有限信息预算" in criterion for criterion in wide_cases[0]["criteria"])
        )

    def test_dataset_check_rejects_changed_retry_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.json"
            dataset = self.dataset()
            dataset["policy"]["automatic_retry"] = True
            path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "automatic_retry"):
                load_dataset(path)

    def test_edit_dataset_locks_target_and_scoped_style_inputs(self) -> None:
        path = SKILL_DIR / "references" / "visual-edit-eval-v1.json"
        dataset = load_dataset(path)
        self.assertEqual(
            [case["intent"] for case in dataset["cases"]],
            ["edit", "edit", "edit"],
        )
        for case in dataset["cases"]:
            contract = case["input_contract"]
            references = [
                {
                    "role": "target",
                    "content_hash": contract["target_sha256"],
                }
            ]
            if contract["style"] is not None:
                references.append(
                    {
                        "role": "style",
                        "item_id": contract["style"]["item_id"],
                        "style_scope": contract["style"]["style_scope"],
                        "content_hash": contract["style"]["content_sha256"],
                    }
                )
            validate_manifest(case, {"references": references})
            references[0]["content_hash"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "target hash changed"):
                validate_manifest(case, {"references": references})

    def test_manga_style_datasets_split_new_and_scoped_edit_paths(self) -> None:
        new_dataset = load_dataset(
            SKILL_DIR / "references" / "visual-manga-style-eval-v1.json"
        )
        edit_dataset = load_dataset(
            SKILL_DIR / "references" / "visual-manga-style-edit-eval-v1.json"
        )
        self.assertTrue(
            all(case["intent"] == "new" for case in new_dataset["cases"])
        )
        self.assertTrue(
            all(case["medium"] == "manga" for case in new_dataset["cases"])
        )
        self.assertTrue(
            all(case["intent"] == "edit" for case in edit_dataset["cases"])
        )
        self.assertTrue(
            all(
                case["change_scope"] in {"character", "scene"}
                for case in edit_dataset["cases"]
            )
        )
        self.assertTrue(
            all(
                case["input_contract"]["style"] is not None
                for case in edit_dataset["cases"]
            )
        )

    def test_candidate_with_two_blind_wins_is_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "passing-run"
            )
            for index, case in enumerate(dataset["cases"]):
                wanted = "candidate" if index < 2 else "baseline"
                judge_run(
                    run_dir,
                    case["id"],
                    self.side_for(run_dir, case["id"], wanted),
                    [],
                    "blind test",
                )
            result = results(run_dir)
            self.assertEqual(result["wins"]["candidate"], 2)
            self.assertTrue(result["promotion_passed"])
            self.assertEqual(result["verdict"], "promote_candidate")
            self.assertTrue((run_dir / "results" / "result.json").is_file())

    def test_critical_candidate_failure_keeps_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "guarded-run"
            )
            for index, case in enumerate(dataset["cases"]):
                candidate_side = self.side_for(run_dir, case["id"], "candidate")
                baseline_side = self.side_for(run_dir, case["id"], "baseline")
                critical = [(candidate_side, "identity")] if index == 0 else []
                choice = baseline_side if index == 0 else candidate_side
                judge_run(run_dir, case["id"], choice, critical, "blind test")
            result = results(run_dir)
            self.assertEqual(result["wins"]["candidate"], 2)
            self.assertFalse(result["promotion_passed"])
            self.assertEqual(result["verdict"], "keep_baseline")

    def test_critical_side_cannot_win_and_two_failed_sides_require_tie(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "absolute-gate-run"
            )
            case = dataset["cases"][0]
            with self.assertRaisesRegex(ValueError, "ineligible"):
                judge_run(
                    run_dir,
                    case["id"],
                    "A",
                    [("A", "manga_medium")],
                    "relative choice is forbidden",
                )
            with self.assertRaisesRegex(ValueError, "tie/both-fail"):
                judge_run(
                    run_dir,
                    case["id"],
                    "A",
                    [("A", "manga_medium"), ("B", "manga_medium")],
                    "both fail",
                )
            judge_run(
                run_dir,
                case["id"],
                "tie",
                [("A", "manga_medium"), ("B", "manga_medium")],
                "both fail",
            )

    def test_explicit_user_feedback_supersedes_immutable_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "human-feedback-run"
            )
            for index, case in enumerate(dataset["cases"]):
                wanted = "candidate" if index < 2 else "baseline"
                judge_run(
                    run_dir,
                    case["id"],
                    self.side_for(run_dir, case["id"], wanted),
                    [],
                    "blind test",
                )
            immutable = results(run_dir)
            self.assertTrue(immutable["promotion_passed"])
            result_hash = file_hash(run_dir / "results" / "result.json")
            record_human_feedback(
                run_dir,
                [
                    (
                        "half-demon-inuyasha-rain-shrine-wide",
                        "candidate",
                        "manga_medium",
                    ),
                    (
                        "half-demon-tessaiga-swing",
                        "baseline",
                        "request_fidelity",
                    ),
                ],
                "explicit user rejection",
            )
            effective = effective_results(run_dir)
            self.assertFalse(effective["promotion_passed"])
            self.assertEqual(effective["verdict"], "keep_baseline")
            self.assertEqual(result_hash, file_hash(run_dir / "results" / "result.json"))
            self.assertEqual(effective["human_feedback_events"], 1)

    def test_wrong_shot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_empty_run(root, "wrong-shot-run")
            case = dataset["cases"][0]
            task, attempt = self.create_attempt(
                root, case, "baseline", shot="profile"
            )
            with self.assertRaisesRegex(ValueError, "shot"):
                record_slot(run_dir, "baseline", case["id"], task, attempt)

    def test_mixed_backend_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_empty_run(root, "backend-run")
            case = dataset["cases"][0]
            task, attempt = self.create_attempt(
                root, case, "baseline", generator="other-backend"
            )
            with self.assertRaisesRegex(ValueError, "generator"):
                record_slot(run_dir, "baseline", case["id"], task, attempt)

    def test_current_attempt_recorder_produces_a_bindable_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_empty_run(root, "recorder-run")
            case = dataset["cases"][0]
            task, _ = self.create_attempt(root, case, "baseline")
            shutil.rmtree(task / "attempts")
            arguments = [
                "record_attempt.py",
                "--task-dir",
                str(task),
                "--status",
                "candidate",
                "--output",
                str(task / "output.png"),
                "--submitted-prompt",
                str(task / "prompt.md"),
                "--generator",
                BACKEND,
                "--duration-seconds",
                "3.5",
                "--preview-check",
                "identity=pass:face and form match official evidence",
                "--preview-check",
                "request=pass:fixed evaluation request is visible",
                "--preview-check",
                "medium=pass:line and tone density match manga evidence",
                "--preview-check",
                "technical=pass:image is complete and artifact free",
            ]
            with patch("sys.argv", arguments), redirect_stdout(io.StringIO()):
                self.assertEqual(record_attempt_main(), 0)
            attempt = task / "attempts" / "001"
            self.assertTrue((attempt / "brief.json").is_file())
            self.assertTrue(
                record_slot(
                    run_dir,
                    "baseline",
                    case["id"],
                    task,
                    attempt,
                ).is_dir()
            )

    def test_second_generation_attempt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_empty_run(root, "retry-run")
            case = dataset["cases"][0]
            task, attempt = self.create_attempt(
                root, case, "baseline", extra_attempt=True
            )
            with self.assertRaisesRegex(ValueError, "exactly one"):
                record_slot(run_dir, "baseline", case["id"], task, attempt)

    def test_error_attempt_is_locked_but_cannot_be_blinded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_empty_run(root, "error-slot-run")
            for case in dataset["cases"]:
                for variant in ("baseline", "candidate"):
                    task, attempt_dir = self.create_attempt(root, case, variant)
                    if case is dataset["cases"][0] and variant == "baseline":
                        attempt_path = attempt_dir / "attempt.json"
                        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
                        attempt["status"] = "error"
                        attempt["output"] = None
                        attempt["output_sha256"] = None
                        attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
                    record_slot(run_dir, variant, case["id"], task, attempt_dir)
            error_slot = (
                run_dir
                / "cases"
                / dataset["cases"][0]["id"]
                / "baseline"
                / "slot.json"
            )
            locked = json.loads(error_slot.read_text(encoding="utf-8"))
            self.assertEqual(locked["attempt_status"], "error")
            self.assertIsNone(locked["output"])
            with self.assertRaisesRegex(ValueError, "no visual output"):
                blind_run(run_dir)
            self.assertFalse((run_dir / "blind").exists())

    def test_changed_reference_pixels_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_empty_run(root, "input-hash-run")
            case = dataset["cases"][0]
            task, attempt = self.create_attempt(root, case, "baseline")
            Image.new("RGB", (12, 12), "magenta").save(task / "reference.png")
            with self.assertRaisesRegex(ValueError, "reference hash mismatch"):
                record_slot(run_dir, "baseline", case["id"], task, attempt)

    def test_recorded_slot_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_recorded_run(root, "immutable-run")
            case = dataset["cases"][0]
            task = root / "source-tasks" / f"{case['id']}-baseline"
            with self.assertRaisesRegex(ValueError, "immutable"):
                record_slot(
                    run_dir,
                    "baseline",
                    case["id"],
                    task,
                    task / "attempts" / "001",
                )

    def test_run_metadata_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, _ = self.prepare_empty_run(Path(directory), "run-lock-test")
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["backend"] = "changed-backend"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metadata changed"):
                load_run(run_dir)

    def test_slot_tampering_blocks_blind_without_partial_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "slot-lock-test", prepare_blind=False
            )
            slot = run_dir / "cases" / dataset["cases"][0]["id"] / "baseline"
            (slot / "prompt.md").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prompt.md lock mismatch"):
                blind_run(run_dir)
            self.assertFalse((run_dir / "blind").exists())

    def test_paired_input_bytes_must_match_before_blinding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_empty_run(root, "paired-input-run")
            for case in dataset["cases"]:
                baseline_task, baseline_attempt = self.create_attempt(
                    root, case, "baseline"
                )
                candidate_task, candidate_attempt = self.create_attempt(
                    root,
                    case,
                    "candidate",
                    reference_color=(80, 30, 20)
                    if case is dataset["cases"][0]
                    else (20, 30, 40),
                )
                record_slot(
                    run_dir,
                    "baseline",
                    case["id"],
                    baseline_task,
                    baseline_attempt,
                )
                record_slot(
                    run_dir,
                    "candidate",
                    case["id"],
                    candidate_task,
                    candidate_attempt,
                )
            with self.assertRaisesRegex(ValueError, "paired inputs differ"):
                blind_run(run_dir)
            self.assertFalse((run_dir / "blind").exists())

    def test_blind_failure_is_atomic_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, dataset = self.prepare_recorded_run(
                root, "atomic-blind-run", prepare_blind=False
            )
            slot = run_dir / "cases" / dataset["cases"][-1]["id"] / "candidate"
            saved = root / "saved-slot"
            slot.rename(saved)
            with self.assertRaises(ValueError):
                blind_run(run_dir)
            self.assertFalse((run_dir / "blind").exists())
            saved.rename(slot)
            self.assertTrue(blind_run(run_dir).is_dir())

    def test_tampered_review_image_blocks_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "review-lock-test"
            )
            for case in dataset["cases"]:
                judge_run(run_dir, case["id"], "A", [], "blind test")
            review = json.loads(
                (run_dir / "blind" / "review-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            image = run_dir / "blind" / review["cases"][0]["A"]["path"]
            Image.new("RGB", (16, 20), "magenta").save(image)
            with self.assertRaisesRegex(ValueError, "image hash mismatch"):
                results(run_dir)
            self.assertFalse((run_dir / "results").exists())

    def test_tampered_judgment_blocks_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "judgment-lock-test"
            )
            for case in dataset["cases"]:
                judge_run(run_dir, case["id"], "A", [], "blind test")
            case_id = dataset["cases"][0]["id"]
            path = run_dir / "blind" / "judgments" / case_id / "judgment.json"
            judgment = json.loads(path.read_text(encoding="utf-8"))
            judgment["choice"] = "B"
            path.write_text(json.dumps(judgment), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "judgment lock changed"):
                results(run_dir)
            self.assertFalse((run_dir / "results").exists())

    def test_result_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "immutable-result-run"
            )
            for case in dataset["cases"]:
                judge_run(run_dir, case["id"], "tie", [], "")
            results(run_dir)
            with self.assertRaisesRegex(ValueError, "already written"):
                results(run_dir)

    def test_activation_guard_uses_effective_feedback_aware_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, dataset = self.prepare_recorded_run(
                Path(directory), "activation-guard-run"
            )
            for index, case in enumerate(dataset["cases"]):
                wanted = "candidate" if index < 2 else "baseline"
                judge_run(
                    run_dir,
                    case["id"],
                    self.side_for(run_dir, case["id"], wanted),
                    [],
                    "blind test",
                )
            results(run_dir)
            self.assertTrue(assert_promoted(run_dir)["promotion_passed"])
            record_human_feedback(
                run_dir,
                [
                    (
                        "half-demon-inuyasha-rain-shrine-wide",
                        "candidate",
                        "manga_medium",
                    )
                ],
                "later explicit rejection",
            )
            with self.assertRaisesRegex(ValueError, "not promotable"):
                assert_promoted(run_dir)


if __name__ == "__main__":
    unittest.main()
