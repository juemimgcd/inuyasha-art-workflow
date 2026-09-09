#!/usr/bin/env python3
"""Snapshot the exact prompt and ordered image files for one generation call."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image
from record_attempt import file_hash
from runtime_provenance import runtime_record
from task_workflow import (
    prompt_compile_report_failures,
    prompt_compile_report_required,
    read_json,
    task_intent,
)
from workflow_common import atomic_write_json, now_iso

DEFAULT_ENDPOINT = "https://chatgpt.com/backend-api/codex/images/edits"
SUBMISSION_SCHEMA_VERSION = 1


def parse_input(value: str) -> tuple[str, Path]:
    role, separator, raw_path = value.partition("=")
    if not separator or not role.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("input must look like ROLE=PATH")
    return role.strip(), Path(raw_path).expanduser().resolve()


def manifest_inputs(manifest: dict) -> list[tuple[str, Path]]:
    inputs: list[tuple[str, Path]] = []
    for entry in manifest.get("references") or []:
        raw_path = entry.get("rendered_path") or entry.get("original_path")
        if not raw_path:
            raise SystemExit(
                f"manifest input {entry.get('item_id', '<unknown>')} has no image path"
            )
        inputs.append((str(entry.get("role", "")), Path(raw_path).expanduser().resolve()))
    return inputs


def image_record(order: int, role: str, path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"generation input is missing: {path}")
    with Image.open(path) as image:
        width, height = image.size
        image_format = image.format
    return {
        "order": order,
        "role": role,
        "path": str(path),
        "sha256": file_hash(path),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "format": image_format,
    }


def validate_generation_submission(
    task_dir: Path, submission: Any, *, require_prepared: bool = True
) -> list[str]:
    if not isinstance(submission, dict):
        return ["generation submission must be an object"]
    failures: list[str] = []
    try:
        brief = read_json(task_dir / "brief.json")
        manifest = read_json(task_dir / "reference-manifest.json")
        window_path = task_dir / "response-window.json"
        window = read_json(window_path) if window_path.is_file() else {}
    except (OSError, ValueError, TypeError) as exc:
        return [f"generation submission context is unreadable: {exc}"]
    prompt_path = Path(str(submission.get("prompt", ""))).expanduser().resolve()
    expected_inputs = manifest_inputs(manifest)
    actual_inputs = submission.get("images", [])
    if not isinstance(actual_inputs, list) or any(
        not isinstance(item, dict) for item in actual_inputs
    ):
        return ["generation submission images must be a list of objects"]
    report_path = task_dir / "prompt-compile.json"
    report_record = submission.get("prompt_compile")

    if "runtime" in submission:
        runtime = submission["runtime"]
        if not isinstance(runtime, dict) or type(runtime.get("schema_version")) is not int or runtime["schema_version"] != 1:
            failures.append("generation submission runtime record is malformed")
        elif require_prepared:
            try:
                current_runtime = runtime_record()
                for field in ("fingerprint", "source_library_sha256"):
                    if runtime.get(field) != current_runtime[field]:
                        failures.append(f"generation submission runtime {field} is stale; prepare a new submission")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                failures.append(f"installed runtime inventory is unreadable: {exc}")

    if (
        type(submission.get("schema_version")) is not int
        or submission.get("schema_version") != SUBMISSION_SCHEMA_VERSION
    ):
        failures.append("generation submission schema is not supported")
    if require_prepared and submission.get("state") != "prepared":
        failures.append("generation submission is not in prepared state")
    started_at = window.get("pre_generation_started_at") or window.get("started_at")
    if not started_at or submission.get("response_started_at") != started_at:
        failures.append("generation submission belongs to a different response window")
    for field, expected in (
        ("task_id", brief.get("task_id") or task_dir.name),
        ("intent", task_intent(brief)),
    ):
        if field in submission and submission[field] != expected:
            failures.append(f"generation submission {field} differs from brief")
    if submission.get("brief_sha256") != file_hash(task_dir / "brief.json"):
        failures.append("generation submission brief hash is stale")
    if submission.get("reference_manifest_sha256") != file_hash(
        task_dir / "reference-manifest.json"
    ):
        failures.append("generation submission manifest hash is stale")
    if not prompt_path.is_file():
        failures.append("generation submission prompt is missing")
    else:
        if submission.get("prompt_sha256") != file_hash(prompt_path):
            failures.append("generation submission prompt hash is stale")
        if "prompt_bytes" in submission and (
            type(submission["prompt_bytes"]) is not int
            or submission["prompt_bytes"] != prompt_path.stat().st_size
        ):
            failures.append("generation submission prompt byte count is stale")
    if prompt_compile_report_required(brief) and not isinstance(report_record, dict):
        failures.append("generation submission is missing prompt-compile.json binding")
    if report_record is not None:
        if not isinstance(report_record, dict):
            failures.append("generation submission prompt_compile must be an object")
        else:
            recorded_path = Path(
                str(report_record.get("path", ""))
            ).expanduser().resolve()
            if recorded_path != report_path.resolve():
                failures.append("generation submission prompt compile path is untracked")
            elif not report_path.is_file():
                failures.append("generation submission prompt compile report is missing")
            elif report_record.get("sha256") != file_hash(report_path):
                failures.append("generation submission prompt compile hash is stale")
            elif report_record.get("bytes") != report_path.stat().st_size:
                failures.append("generation submission prompt compile byte count is stale")
            else:
                try:
                    report = read_json(report_path)
                except (OSError, ValueError, TypeError) as exc:
                    failures.append(
                        f"generation submission prompt compile is unreadable: {exc}"
                    )
                    report = None
                compiled_prompt_path = task_dir / "prompt.md"
                if not compiled_prompt_path.is_file():
                    failures.append("compiled prompt for prompt-compile.json is missing")
                elif report is not None:
                    failures.extend(
                        prompt_compile_report_failures(
                            brief,
                            manifest,
                            compiled_prompt_path.read_text(encoding="utf-8"),
                            report,
                        )
                    )
    verified_input_bytes = 0
    verified_input_count = 0
    if len(actual_inputs) != len(expected_inputs):
        failures.append("generation submission input count differs from manifest")
    else:
        for index, ((expected_role, expected_path), actual) in enumerate(
            zip(expected_inputs, actual_inputs, strict=True), start=1
        ):
            actual_path = Path(str(actual.get("path", ""))).expanduser().resolve()
            if (
                type(actual.get("order")) is not int
                or actual.get("order") != index
                or actual.get("role") != expected_role
            ):
                failures.append(f"generation submission input {index} role/order changed")
            if actual_path != expected_path:
                failures.append(f"generation submission input {index} path is untracked")
            elif not actual_path.is_file():
                failures.append(f"generation submission input {index} is missing")
            else:
                try:
                    current = image_record(index, expected_role, actual_path)
                except (OSError, ValueError) as exc:
                    failures.append(
                        f"generation submission input {index} is unreadable: {exc}"
                    )
                    continue
                verified_input_count += 1
                verified_input_bytes += current["bytes"]
                if actual.get("sha256") != current["sha256"]:
                    failures.append(f"generation submission input {index} hash is stale")
                # Older schema-1 snapshots may omit metadata. Validate every
                # field they do record against the file, not against other claims.
                for field in ("bytes", "width", "height"):
                    if field in actual and (
                        type(actual[field]) is not int
                        or actual[field] != current[field]
                    ):
                        failures.append(
                            f"generation submission input {index} {field} is stale"
                        )
                if "format" in actual and actual["format"] != current["format"]:
                    failures.append(f"generation submission input {index} format is stale")

    if "input_bytes" in submission and verified_input_count == len(expected_inputs):
        if (
            type(submission["input_bytes"]) is not int
            or submission["input_bytes"] != verified_input_bytes
        ):
            failures.append("generation submission total input byte count is stale")

    roles = [str(item.get("role", "")) for item in actual_inputs]
    intent = task_intent(brief)
    if intent in {"edit", "microfix"}:
        if roles.count("target") != 1 or not roles or roles[0] != "target":
            failures.append(f"{intent} submission requires exactly one first target")
    elif "target" in roles:
        failures.append(
            "new task cannot submit a target; create a child edit task for follow-up changes"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument(
        "--input",
        type=parse_input,
        action="append",
        default=[],
        help="Exact ordered ROLE=PATH image input. Defaults to manifest order.",
    )
    parser.add_argument("--submitted-prompt", type=Path)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--transport", default="manifest-tracked")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    task_dir = args.task_dir.expanduser().resolve()
    brief = read_json(task_dir / "brief.json")
    manifest = read_json(task_dir / "reference-manifest.json")
    window_path = task_dir / "response-window.json"
    if not window_path.is_file():
        raise SystemExit("start_response_window.py must run before submission preparation")
    window = read_json(window_path)
    if window.get("phase") != "pre-generation":
        raise SystemExit("response window must be in pre-generation phase")
    response_started_at = window.get("pre_generation_started_at") or window.get(
        "started_at"
    )
    if not response_started_at:
        raise SystemExit("response window has no start timestamp")

    current_path = task_dir / "generation-submission.json"
    if current_path.is_file():
        current = read_json(current_path)
        if current.get("state") == "submitted":
            raise SystemExit("an unrecorded submitted generation already exists")

    prompt = (
        args.submitted_prompt.expanduser().resolve()
        if args.submitted_prompt
        else task_dir / "prompt.md"
    )
    if not prompt.is_file():
        raise SystemExit(f"submitted prompt is missing: {prompt}")
    expected = manifest_inputs(manifest)
    inputs = args.input or expected
    if inputs != expected:
        raise SystemExit(
            "explicit generation inputs must exactly match manifest role, order, and path"
        )
    images = [
        image_record(index, role, path)
        for index, (role, path) in enumerate(inputs, start=1)
    ]
    report_path = task_dir / "prompt-compile.json"
    if prompt_compile_report_required(brief) and not report_path.is_file():
        raise SystemExit(
            "prompt-compile.json is missing; run compile_prompt.py before submission"
        )
    submission = {
        "schema_version": SUBMISSION_SCHEMA_VERSION,
        "state": "prepared",
        "prepared_at": now_iso(),
        "response_started_at": response_started_at,
        "task_id": brief.get("task_id") or task_dir.name,
        "intent": task_intent(brief),
        "endpoint": args.endpoint,
        "transport": args.transport,
        "prompt": str(prompt),
        "prompt_sha256": file_hash(prompt),
        "prompt_bytes": prompt.stat().st_size,
        "brief_sha256": file_hash(task_dir / "brief.json"),
        "reference_manifest_sha256": file_hash(
            task_dir / "reference-manifest.json"
        ),
        "prompt_compile": (
            {
                "path": str(report_path),
                "sha256": file_hash(report_path),
                "bytes": report_path.stat().st_size,
            }
            if report_path.is_file()
            else None
        ),
        "images": images,
        "input_bytes": sum(int(image["bytes"]) for image in images),
        "runtime": runtime_record(),
    }
    failures = validate_generation_submission(task_dir, submission)
    if failures:
        raise SystemExit("; ".join(failures))
    atomic_write_json(current_path, submission)
    if args.json:
        print(json.dumps(submission, ensure_ascii=False, indent=2))
    else:
        print(current_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
