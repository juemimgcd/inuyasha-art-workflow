from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continue_art_task import continuation_intent
from init_art_task import qa_items
from prepare_generation_submission import image_record, validate_generation_submission
from prepare_quick_edit import main as prepare_quick_edit_main
from record_attempt import file_hash
from record_attempt import main as record_attempt_main
from start_response_window import main as start_response_window_main
from task_workflow import compile_prompt
from technical_failures import transport_retry_exhausted


class EditWorkflowHardeningTests(unittest.TestCase):
    def test_target_only_quick_edit_does_not_require_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.png"
            Image.new("RGB", (24, 16), "white").save(target)
            with (
                patch(
                    "sys.argv",
                    [
                        "prepare_quick_edit.py",
                        "--workflow-root",
                        str(root / "workflow"),
                        "--slug",
                        "target-only",
                        "--request",
                        "只修改右手，其他内容保持不变",
                        "--target",
                        str(target),
                        "--change-category",
                        "anatomy",
                        "--medium",
                        "manga",
                        "--shot",
                        "wide-shot",
                    ],
                ),
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(prepare_quick_edit_main(), 0)
            result = json.loads(output.getvalue())
            task = Path(result["task_dir"])
            self.assertTrue(result["ready_for_generation"])
            self.assertTrue((task / "generation-submission.json").is_file())
            manifest = json.loads(
                (task / "reference-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [entry["role"] for entry in manifest["references"]], ["target"]
            )

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
                    {
                        "references": [
                            {"role": "target", "rendered_path": str(target)}
                        ]
                    }
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
                    {
                        "references": [
                            {"role": "target", "rendered_path": str(target)}
                        ]
                    }
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
                        "identity=pass",
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

    def test_wide_manga_medium_edit_locks_target_staging(self) -> None:
        brief = {
            "intent": "edit",
            "medium": "manga",
            "shot": "wide-shot",
            "request": "继续贴近原作漫画的场景画法",
            "change_request": "继续贴近原作漫画的场景画法",
            "invariants": [],
        }
        prompt = compile_prompt(brief, {"references": []})
        self.assertIn("Wide-shot preservation lock", prompt)
        self.assertIn("character scale and placement", prompt)
        self.assertIn("Do not enlarge the character", prompt)
        self.assertIn("Economy is not uniform simplification", prompt)

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


if __name__ == "__main__":
    unittest.main()
