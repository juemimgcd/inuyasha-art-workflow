#!/usr/bin/env python3
"""Snapshot the exact prompt and ordered image files for one generation call."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image
from record_attempt import file_hash
from task_workflow import read_json, task_intent
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
    task_dir: Path, submission: dict, *, require_prepared: bool = True
) -> list[str]:
    failures: list[str] = []
    brief = read_json(task_dir / "brief.json")
    manifest = read_json(task_dir / "reference-manifest.json")
    prompt_path = Path(str(submission.get("prompt", ""))).expanduser().resolve()
    window_path = task_dir / "response-window.json"
    window = read_json(window_path) if window_path.is_file() else {}
    expected_inputs = manifest_inputs(manifest)
    actual_inputs = submission.get("images") or []

    if submission.get("schema_version") != SUBMISSION_SCHEMA_VERSION:
        failures.append("generation submission schema is not supported")
    if require_prepared and submission.get("state") != "prepared":
        failures.append("generation submission is not in prepared state")
    if submission.get("response_started_at") != (
        window.get("pre_generation_started_at") or window.get("started_at")
    ):
        failures.append("generation submission belongs to a different response window")
    if submission.get("brief_sha256") != file_hash(task_dir / "brief.json"):
        failures.append("generation submission brief hash is stale")
    if submission.get("reference_manifest_sha256") != file_hash(
        task_dir / "reference-manifest.json"
    ):
        failures.append("generation submission manifest hash is stale")
    if not prompt_path.is_file():
        failures.append("generation submission prompt is missing")
    elif submission.get("prompt_sha256") != file_hash(prompt_path):
        failures.append("generation submission prompt hash is stale")
    if len(actual_inputs) != len(expected_inputs):
        failures.append("generation submission input count differs from manifest")
    else:
        for index, ((expected_role, expected_path), actual) in enumerate(
            zip(expected_inputs, actual_inputs, strict=True), start=1
        ):
            actual_path = Path(str(actual.get("path", ""))).expanduser().resolve()
            if actual.get("order") != index or actual.get("role") != expected_role:
                failures.append(f"generation submission input {index} role/order changed")
            if actual_path != expected_path:
                failures.append(f"generation submission input {index} path is untracked")
            elif not actual_path.is_file():
                failures.append(f"generation submission input {index} is missing")
            elif actual.get("sha256") != file_hash(actual_path):
                failures.append(f"generation submission input {index} hash is stale")

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
    inputs = args.input or manifest_inputs(manifest)
    expected = manifest_inputs(manifest)
    if inputs != expected:
        raise SystemExit(
            "explicit generation inputs must exactly match manifest role, order, and path"
        )
    images = [
        image_record(index, role, path)
        for index, (role, path) in enumerate(inputs, start=1)
    ]
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
        "images": images,
        "input_bytes": sum(int(image["bytes"]) for image in images),
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
