#!/usr/bin/env python3
"""Prepare, lock, blind-review, and score a three-case visual A/B gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from workflow_common import (
    SHOT_VALUES,
    atomic_write_json,
    atomic_write_text,
    load_config,
    workflow_root,
)

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = SKILL_DIR / "references" / "visual-eval-v2.json"
VARIANTS = ("baseline", "candidate")
CHOICES = ("A", "B", "tie")
CRITICAL_CATEGORIES = (
    "identity",
    "manga_medium",
    "request_fidelity",
    "anatomy_contact",
    "technical",
)
VISUAL_ATTEMPT_STATUSES = {"accepted", "candidate", "rejected"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object: {path}")
    return value


def require_safe_name(value: Any, label: str) -> str:
    name = str(value or "").strip()
    if not SAFE_NAME.fullmatch(name):
        raise ValueError(f"{label} must be a safe portable name: {name}")
    return name


def resolve_locked_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} path is missing")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} path must be relative: {value}")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} path escapes its lock directory: {value}") from exc
    return resolved


def resolve_attempt_output(task_dir: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("attempt output path is missing")
    output = Path(value).expanduser()
    if not output.is_absolute():
        output = task_dir / output
    return output.resolve()


def verify_image(path: Path) -> None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    except (ImportError, OSError, ValueError) as exc:
        raise ValueError(f"invalid image: {path}: {exc}") from exc


def load_dataset(path: Path) -> dict[str, Any]:
    dataset = read_json(path, "visual eval dataset")
    if dataset.get("schema_version") != 1:
        raise ValueError("visual eval dataset schema_version must be 1")
    require_safe_name(dataset.get("id"), "dataset id")
    policy = dataset.get("policy")
    if not isinstance(policy, dict):
        raise TypeError("visual eval dataset policy is missing")
    expected_policy = {
        "variants": list(VARIANTS),
        "cases_per_variant": 3,
        "total_images": 6,
        "single_generation_per_slot": True,
        "automatic_retry": False,
        "blind_pairwise_review": True,
    }
    for field, expected in expected_policy.items():
        if policy.get(field) != expected:
            raise ValueError(f"visual eval policy {field} must be {expected!r}")
    promotion = dataset.get("promotion")
    expected_promotion = {
        "minimum_candidate_wins": 2,
        "maximum_candidate_critical_failures": 0,
        "ties_keep_baseline": True,
    }
    if not isinstance(promotion, dict):
        raise TypeError("visual eval promotion policy is missing")
    for field, expected in expected_promotion.items():
        if promotion.get(field) != expected:
            raise ValueError(f"visual eval promotion {field} must be {expected!r}")
    if dataset.get("critical_categories") != list(CRITICAL_CATEGORIES):
        raise ValueError("visual eval critical categories do not match the contract")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("visual eval dataset must contain exactly three cases")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("visual eval cases must be JSON objects")
        case_id = require_safe_name(case.get("id"), "case id")
        if case_id in seen:
            raise ValueError(f"duplicate visual eval case: {case_id}")
        seen.add(case_id)
        for field in ("title", "intent", "medium", "request", "aspect_ratio"):
            if not str(case.get(field, "")).strip():
                raise ValueError(f"visual eval case {case_id} requires {field}")
        if case.get("shot") not in SHOT_VALUES:
            raise ValueError(f"visual eval case {case_id} has invalid shot")
        forms = case.get("identity_forms")
        if not isinstance(forms, dict) or not forms or not all(
            str(subject).strip() and str(form).strip()
            for subject, form in forms.items()
        ):
            raise ValueError(f"visual eval case {case_id} lacks identity forms")
        criteria = case.get("criteria")
        if not isinstance(criteria, list) or not criteria or not all(
            isinstance(item, str) and item.strip() for item in criteria
        ):
            raise ValueError(f"visual eval case {case_id} lacks criteria")
    return dataset


def case_by_id(dataset: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in dataset["cases"]:
        if case["id"] == case_id:
            return case
    raise ValueError(f"unknown visual eval case: {case_id}")


def validate_brief(case: dict[str, Any], brief: dict[str, Any]) -> None:
    expected = {
        "intent": case["intent"],
        "medium": case["medium"],
        "request": case["request"],
        "identity_forms": case["identity_forms"],
        "shot": case["shot"],
        "aspect_ratio": case["aspect_ratio"],
    }
    for field, value in expected.items():
        if brief.get(field) != value:
            raise ValueError(f"task {field} does not match case {case['id']}")


def load_run(
    run_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_path = run_dir / "run.json"
    lock_path = run_dir / "run-lock.json"
    dataset_path = run_dir / "dataset.json"
    run = read_json(run_path, "visual eval run")
    lock = read_json(lock_path, "visual eval run lock")
    dataset = load_dataset(dataset_path)
    if lock.get("schema_version") != 1:
        raise ValueError("visual eval run lock schema_version must be 1")
    if file_hash(run_path) != lock.get("run_sha256"):
        raise ValueError("visual eval run metadata changed after preparation")
    if run.get("schema_version") != 2:
        raise ValueError("visual eval run schema_version must be 2")
    if run.get("dataset_id") != dataset["id"]:
        raise ValueError("visual eval run dataset id does not match")
    if file_hash(dataset_path) != run.get("dataset_sha256"):
        raise ValueError("visual eval dataset snapshot changed")
    if json_hash(dataset) != run.get("dataset_content_sha256"):
        raise ValueError("visual eval dataset content changed")
    run_id = require_safe_name(run.get("run_id"), "run id")
    if run_dir.name != run_id:
        raise ValueError("visual eval run directory does not match run id")
    labels = run.get("labels")
    if not isinstance(labels, dict) or set(labels) != set(VARIANTS):
        raise ValueError("visual eval run labels are invalid")
    if not all(str(labels[variant]).strip() for variant in VARIANTS):
        raise ValueError("visual eval run labels must be non-empty")
    if labels["baseline"] == labels["candidate"]:
        raise ValueError("baseline and candidate labels must differ")
    if not str(run.get("backend", "")).strip():
        raise ValueError("visual eval run backend is missing")
    expected_cases = [case["id"] for case in dataset["cases"]]
    if run.get("case_ids") != expected_cases:
        raise ValueError("visual eval run case list does not match dataset")
    expected_flags = {
        "required_images": 6,
        "single_generation_per_slot": True,
        "automatic_retry": False,
    }
    for field, expected in expected_flags.items():
        if run.get(field) != expected:
            raise ValueError(f"visual eval run {field} changed")
    return run, dataset, lock


def prepare_run(
    dataset_path: Path,
    root: Path,
    run_id: str,
    baseline_label: str,
    candidate_label: str,
    backend: str,
) -> Path:
    dataset = load_dataset(dataset_path)
    run_id = require_safe_name(run_id, "run id")
    if not baseline_label.strip() or not candidate_label.strip():
        raise ValueError("baseline and candidate labels must be non-empty")
    if baseline_label == candidate_label:
        raise ValueError("baseline and candidate labels must differ")
    if not backend.strip():
        raise ValueError("backend must be non-empty")
    parent = root / "visual-evaluations" / dataset["id"]
    parent.mkdir(parents=True, exist_ok=True)
    run_dir = parent / run_id
    if run_dir.exists():
        raise ValueError(f"visual eval run already exists: {run_dir}")
    staging = Path(tempfile.mkdtemp(prefix=f".{run_id}-", dir=parent))
    try:
        snapshot = staging / "dataset.json"
        shutil.copy2(dataset_path, snapshot)
        for case in dataset["cases"]:
            case_dir = staging / "cases" / case["id"]
            case_dir.mkdir(parents=True)
            atomic_write_json(case_dir / "spec.json", case)
        run = {
            "schema_version": 2,
            "dataset_id": dataset["id"],
            "dataset_sha256": file_hash(snapshot),
            "dataset_content_sha256": json_hash(dataset),
            "prepared_at": now_iso(),
            "run_id": run_id,
            "labels": {
                "baseline": baseline_label,
                "candidate": candidate_label,
            },
            "backend": backend,
            "case_ids": [case["id"] for case in dataset["cases"]],
            "required_images": 6,
            "single_generation_per_slot": True,
            "automatic_retry": False,
        }
        atomic_write_json(staging / "run.json", run)
        atomic_write_json(
            staging / "run-lock.json",
            {"schema_version": 1, "run_sha256": file_hash(staging / "run.json")},
        )
        staging.rename(run_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return run_dir


def load_attempt(
    run: dict[str, Any],
    case: dict[str, Any],
    task_dir: Path,
    attempt_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    expected_root = (task_dir / "attempts").resolve()
    attempt_dir = attempt_dir.resolve()
    if attempt_dir.parent != expected_root or attempt_dir.name != "001":
        raise ValueError("visual eval requires task attempts/001")
    attempt_dirs = (
        sorted(
            path.name
            for path in expected_root.iterdir()
            if path.is_dir() and path.name.isdigit()
        )
        if expected_root.is_dir()
        else []
    )
    if attempt_dirs != ["001"]:
        raise ValueError("visual eval task must contain exactly one generation attempt")
    attempt = read_json(attempt_dir / "attempt.json", "generation attempt")
    if attempt.get("schema_version") != 1 or attempt.get("attempt") != 1:
        raise ValueError("visual eval requires attempt schema 1 and attempt number 1")
    if attempt.get("status") not in VISUAL_ATTEMPT_STATUSES:
        raise ValueError("visual eval attempt must contain a visual output")
    if attempt.get("generator") != run["backend"]:
        raise ValueError("visual eval attempt generator does not match run backend")
    duration = attempt.get("generation_seconds")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise ValueError("visual eval attempt requires positive generation_seconds")
    snapshot_paths = {
        "brief_sha256": attempt_dir / "brief.json",
        "compiled_prompt_sha256": attempt_dir / "prompt.md",
        "submitted_prompt_sha256": attempt_dir / "submitted-prompt.md",
        "reference_manifest_sha256": attempt_dir / "reference-manifest.json",
    }
    for field, path in snapshot_paths.items():
        if not path.is_file() or file_hash(path) != attempt.get(field):
            raise ValueError(f"generation attempt {field} snapshot mismatch")
    brief = read_json(attempt_dir / "brief.json", "attempt brief snapshot")
    manifest = read_json(
        attempt_dir / "reference-manifest.json",
        "attempt reference manifest snapshot",
    )
    validate_brief(case, brief)
    references = manifest.get("references")
    if not isinstance(references, list) or not references:
        raise ValueError("visual eval attempt requires prepared references")
    item_ids = [entry.get("item_id") for entry in references]
    if attempt.get("reference_item_ids") != item_ids:
        raise ValueError("attempt reference item IDs do not match its manifest")
    output = resolve_attempt_output(task_dir, attempt.get("output"))
    if not output.is_file() or file_hash(output) != attempt.get("output_sha256"):
        raise ValueError("generation attempt output hash mismatch")
    verify_image(output)
    return brief, manifest, attempt, output


def record_slot(
    run_dir: Path,
    variant: str,
    case_id: str,
    task_dir: Path,
    attempt_dir: Path,
) -> Path:
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}")
    run, dataset, run_lock = load_run(run_dir)
    case = case_by_id(dataset, case_id)
    task_dir = task_dir.expanduser().resolve()
    attempt_dir = attempt_dir.expanduser().resolve()
    _brief, manifest, attempt, output = load_attempt(
        run,
        case,
        task_dir,
        attempt_dir,
    )
    slot = run_dir / "cases" / case_id / variant
    if slot.exists():
        raise ValueError(f"visual eval slot is immutable and already recorded: {slot}")
    prepared_sources: list[tuple[int, dict[str, Any], Path]] = []
    for index, entry in enumerate(manifest["references"], 1):
        if not isinstance(entry, dict):
            raise TypeError("attempt manifest references must be objects")
        source = Path(str(entry.get("rendered_path", ""))).expanduser()
        if not source.is_absolute():
            source = task_dir / source
        source = source.resolve()
        if not source.is_file():
            raise ValueError(f"prepared reference is missing: {source}")
        verify_image(source)
        expected_hash = entry.get("rendered_content_hash") or entry.get(
            "content_hash"
        )
        if not isinstance(expected_hash, str) or file_hash(source) != expected_hash:
            raise ValueError(f"prepared reference hash mismatch: {source}")
        prepared_sources.append((index, entry, source))
    slot.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{variant}-", dir=slot.parent))
    try:
        snapshots = {
            "brief.json": attempt_dir / "brief.json",
            "prompt.md": attempt_dir / "prompt.md",
            "submitted-prompt.md": attempt_dir / "submitted-prompt.md",
            "reference-manifest.json": attempt_dir / "reference-manifest.json",
            "attempt.json": attempt_dir / "attempt.json",
        }
        for name, source in snapshots.items():
            shutil.copy2(source, staging / name)
        inputs_dir = staging / "inputs"
        inputs_dir.mkdir()
        inputs = []
        for index, entry, source in prepared_sources:
            suffix = source.suffix.casefold() or ".img"
            role = require_safe_name(
                entry.get("role") or "reference",
                "reference role",
            )
            copied = inputs_dir / f"{index:02d}-{role}{suffix}"
            shutil.copy2(source, copied)
            inputs.append(
                {
                    "order": index,
                    "role": entry.get("role"),
                    "item_id": entry.get("item_id"),
                    "path": str(copied.relative_to(staging)),
                    "sha256": file_hash(copied),
                    "original_path": str(source),
                }
            )
        atomic_write_json(
            staging / "inputs.json",
            {
                "schema_version": 1,
                "case_id": case_id,
                "variant": variant,
                "input_order": inputs,
            },
        )
        suffix = output.suffix.casefold() or ".png"
        locked_output = staging / f"output{suffix}"
        shutil.copy2(output, locked_output)
        atomic_write_json(
            staging / "slot.json",
            {
                "schema_version": 2,
                "case_id": case_id,
                "variant": variant,
                "run_sha256": run_lock["run_sha256"],
                "variant_label": run["labels"][variant],
                "backend": run["backend"],
                "recorded_at": now_iso(),
                "task_dir": str(task_dir),
                "attempt_source": str(attempt_dir),
                "attempt_number": 1,
                "attempt_status": attempt["status"],
                "generation_seconds": attempt["generation_seconds"],
                "brief_sha256": file_hash(staging / "brief.json"),
                "prompt_sha256": file_hash(staging / "prompt.md"),
                "submitted_prompt_sha256": file_hash(
                    staging / "submitted-prompt.md"
                ),
                "reference_manifest_sha256": file_hash(
                    staging / "reference-manifest.json"
                ),
                "attempt_sha256": file_hash(staging / "attempt.json"),
                "inputs_sha256": file_hash(staging / "inputs.json"),
                "output": locked_output.name,
                "output_sha256": file_hash(locked_output),
            },
        )
        staging.rename(slot)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return slot


def checked_slot(
    run_dir: Path,
    case: dict[str, Any],
    variant: str,
    run: dict[str, Any],
    run_lock: dict[str, Any],
) -> dict[str, Any]:
    slot = run_dir / "cases" / case["id"] / variant
    record = read_json(slot / "slot.json", "visual eval slot")
    expected = {
        "schema_version": 2,
        "case_id": case["id"],
        "variant": variant,
        "run_sha256": run_lock["run_sha256"],
        "variant_label": run["labels"][variant],
        "backend": run["backend"],
        "attempt_number": 1,
    }
    for field, value in expected.items():
        if record.get(field) != value:
            raise ValueError(f"slot {case['id']}/{variant} changed field {field}")
    locked_files = {
        "brief_sha256": "brief.json",
        "prompt_sha256": "prompt.md",
        "submitted_prompt_sha256": "submitted-prompt.md",
        "reference_manifest_sha256": "reference-manifest.json",
        "attempt_sha256": "attempt.json",
        "inputs_sha256": "inputs.json",
    }
    for field, name in locked_files.items():
        path = slot / name
        if not path.is_file() or file_hash(path) != record.get(field):
            raise ValueError(f"slot {case['id']}/{variant} {name} lock mismatch")
    brief = read_json(slot / "brief.json", "locked slot brief")
    validate_brief(case, brief)
    manifest = read_json(
        slot / "reference-manifest.json",
        "locked slot reference manifest",
    )
    attempt = read_json(slot / "attempt.json", "locked slot attempt")
    if attempt.get("attempt") != 1 or attempt.get("generator") != run["backend"]:
        raise ValueError(f"slot {case['id']}/{variant} attempt metadata changed")
    if attempt.get("status") != record.get("attempt_status"):
        raise ValueError(f"slot {case['id']}/{variant} attempt status changed")
    if attempt.get("generation_seconds") != record.get("generation_seconds"):
        raise ValueError(f"slot {case['id']}/{variant} generation time changed")
    if attempt.get("compiled_prompt_sha256") != record.get("prompt_sha256"):
        raise ValueError(f"slot {case['id']}/{variant} compiled prompt changed")
    if attempt.get("submitted_prompt_sha256") != record.get(
        "submitted_prompt_sha256"
    ):
        raise ValueError(f"slot {case['id']}/{variant} submitted prompt changed")
    if attempt.get("brief_sha256") != record.get("brief_sha256"):
        raise ValueError(f"slot {case['id']}/{variant} brief changed")
    if attempt.get("reference_manifest_sha256") != record.get(
        "reference_manifest_sha256"
    ):
        raise ValueError(f"slot {case['id']}/{variant} manifest changed")
    references = manifest.get("references")
    inputs = read_json(slot / "inputs.json", "locked slot inputs")
    if (
        inputs.get("schema_version") != 1
        or inputs.get("case_id") != case["id"]
        or inputs.get("variant") != variant
        or not isinstance(inputs.get("input_order"), list)
        or not isinstance(references, list)
        or len(inputs["input_order"]) != len(references)
    ):
        raise ValueError(f"slot {case['id']}/{variant} inputs are invalid")
    for index, (item, reference) in enumerate(
        zip(inputs["input_order"], references),
        1,
    ):
        if (
            item.get("order") != index
            or item.get("role") != reference.get("role")
            or item.get("item_id") != reference.get("item_id")
        ):
            raise ValueError(f"slot {case['id']}/{variant} input order changed")
        path = resolve_locked_path(slot, item.get("path"), "slot input")
        if not path.is_file() or file_hash(path) != item.get("sha256"):
            raise ValueError(f"slot {case['id']}/{variant} input hash mismatch")
        verify_image(path)
    output = resolve_locked_path(slot, record.get("output"), "slot output")
    if not output.is_file() or file_hash(output) != record.get("output_sha256"):
        raise ValueError(f"slot {case['id']}/{variant} output hash mismatch")
    if attempt.get("output_sha256") != record.get("output_sha256"):
        raise ValueError(f"slot {case['id']}/{variant} attempt output changed")
    verify_image(output)
    return {
        "record": record,
        "output": output,
        "slot_sha256": file_hash(slot / "slot.json"),
    }


def blind_run(run_dir: Path) -> Path:
    run, dataset, run_lock = load_run(run_dir)
    blind_dir = run_dir / "blind"
    if blind_dir.exists():
        raise ValueError("blind review is immutable and already prepared")
    slots: dict[str, dict[str, dict[str, Any]]] = {}
    for case in dataset["cases"]:
        slots[case["id"]] = {
            variant: checked_slot(run_dir, case, variant, run, run_lock)
            for variant in VARIANTS
        }
    staging = Path(tempfile.mkdtemp(prefix=".blind-", dir=run_dir))
    try:
        review_dir = staging / "review"
        review_dir.mkdir()
        (staging / "judgments").mkdir()
        mapping: dict[str, dict[str, dict[str, str]]] = {}
        review_cases = []
        for case in dataset["cases"]:
            case_id = case["id"]
            swap = (
                hashlib.sha256(f"{run['run_id']}:{case_id}".encode()).digest()[0]
                % 2
            )
            variants = (
                {"A": "candidate", "B": "baseline"}
                if swap
                else {"A": "baseline", "B": "candidate"}
            )
            mapping[case_id] = {}
            visible: dict[str, dict[str, str]] = {}
            for side, variant in variants.items():
                slot = slots[case_id][variant]
                source = slot["output"]
                destination = review_dir / f"{case_id}-{side}{source.suffix}"
                shutil.copy2(source, destination)
                digest = file_hash(destination)
                relative = str(destination.relative_to(staging))
                visible[side] = {"path": relative, "sha256": digest}
                mapping[case_id][side] = {
                    "variant": variant,
                    "slot_sha256": slot["slot_sha256"],
                    "output_sha256": slot["record"]["output_sha256"],
                }
            review_cases.append(
                {
                    "case_id": case_id,
                    "title": case["title"],
                    "request": case["request"],
                    "criteria": case["criteria"],
                    "A": visible["A"],
                    "B": visible["B"],
                }
            )
        atomic_write_json(
            staging / "blind-key.json",
            {
                "schema_version": 2,
                "run_sha256": run_lock["run_sha256"],
                "mapping": mapping,
            },
        )
        atomic_write_json(
            staging / "review-manifest.json",
            {
                "schema_version": 2,
                "run_sha256": run_lock["run_sha256"],
                "prepared_at": now_iso(),
                "cases": review_cases,
            },
        )
        atomic_write_json(
            staging / "blind-lock.json",
            {
                "schema_version": 1,
                "run_sha256": run_lock["run_sha256"],
                "blind_key_sha256": file_hash(staging / "blind-key.json"),
                "review_manifest_sha256": file_hash(
                    staging / "review-manifest.json"
                ),
            },
        )
        staging.rename(blind_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return blind_dir / "review"


def validate_blind(
    run_dir: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    str,
]:
    run, dataset, run_lock = load_run(run_dir)
    blind_dir = run_dir / "blind"
    lock = read_json(blind_dir / "blind-lock.json", "blind review lock")
    key_path = blind_dir / "blind-key.json"
    review_path = blind_dir / "review-manifest.json"
    if lock.get("schema_version") != 1:
        raise ValueError("blind review lock schema_version must be 1")
    if lock.get("run_sha256") != run_lock["run_sha256"]:
        raise ValueError("blind review run lock changed")
    if file_hash(key_path) != lock.get("blind_key_sha256"):
        raise ValueError("blind review key changed")
    if file_hash(review_path) != lock.get("review_manifest_sha256"):
        raise ValueError("blind review manifest changed")
    key = read_json(key_path, "blind review key")
    review = read_json(review_path, "blind review manifest")
    if (
        key.get("schema_version") != 2
        or review.get("schema_version") != 2
        or key.get("run_sha256") != run_lock["run_sha256"]
        or review.get("run_sha256") != run_lock["run_sha256"]
    ):
        raise ValueError("blind review metadata does not match the run")
    review_cases = review.get("cases")
    if not isinstance(review_cases, list):
        raise TypeError("blind review cases are missing")
    by_id = {
        row.get("case_id"): row
        for row in review_cases
        if isinstance(row, dict)
    }
    expected_ids = [case["id"] for case in dataset["cases"]]
    if len(by_id) != 3 or [row.get("case_id") for row in review_cases] != expected_ids:
        raise ValueError("blind review case list changed")
    mapping = key.get("mapping")
    if not isinstance(mapping, dict) or set(mapping) != set(expected_ids):
        raise ValueError("blind review mapping changed")
    for case in dataset["cases"]:
        case_id = case["id"]
        row = by_id[case_id]
        if (
            row.get("title") != case["title"]
            or row.get("request") != case["request"]
            or row.get("criteria") != case["criteria"]
        ):
            raise ValueError(f"blind review case metadata changed: {case_id}")
        case_mapping = mapping.get(case_id)
        if not isinstance(case_mapping, dict) or set(case_mapping) != {"A", "B"}:
            raise ValueError(f"blind review sides changed: {case_id}")
        variants = {
            value.get("variant")
            for value in case_mapping.values()
            if isinstance(value, dict)
        }
        if variants != set(VARIANTS):
            raise ValueError(f"blind review variants changed: {case_id}")
        for side in ("A", "B"):
            visible = row.get(side)
            mapped = case_mapping.get(side)
            if not isinstance(visible, dict) or not isinstance(mapped, dict):
                raise TypeError(f"blind review side is invalid: {case_id}/{side}")
            image = resolve_locked_path(
                blind_dir,
                visible.get("path"),
                "blind review image",
            )
            if not image.is_file() or file_hash(image) != visible.get("sha256"):
                raise ValueError(f"blind review image hash mismatch: {case_id}/{side}")
            verify_image(image)
            variant = mapped["variant"]
            slot = checked_slot(run_dir, case, variant, run, run_lock)
            if slot["slot_sha256"] != mapped.get("slot_sha256"):
                raise ValueError(f"blind review slot changed: {case_id}/{side}")
            if slot["record"]["output_sha256"] != mapped.get("output_sha256"):
                raise ValueError(f"blind review output lock changed: {case_id}/{side}")
            if visible["sha256"] != mapped["output_sha256"]:
                raise ValueError(f"blind review image source changed: {case_id}/{side}")
    return run, dataset, review, key, file_hash(blind_dir / "blind-lock.json")


def judge_run(
    run_dir: Path,
    case_id: str,
    choice: str,
    critical: list[tuple[str, str]],
    note: str,
) -> None:
    _, dataset, _, _, blind_lock_sha256 = validate_blind(run_dir)
    case_by_id(dataset, case_id)
    if choice not in CHOICES:
        raise ValueError(f"choice must be one of {CHOICES}")
    allowed = set(dataset["critical_categories"])
    for side, category in critical:
        if side not in {"A", "B"} or category not in allowed:
            raise ValueError(f"invalid critical failure: {side}={category}")
    critical_sides = {side for side, _ in critical}
    if critical_sides == {"A", "B"} and choice != "tie":
        raise ValueError(
            "both sides have critical failures; the judgment must be tie/both-fail"
        )
    if len(critical_sides) == 1:
        failed_side = next(iter(critical_sides))
        eligible_side = "B" if failed_side == "A" else "A"
        if choice != eligible_side:
            raise ValueError(
                f"side {failed_side} has a critical failure and is ineligible; "
                f"choose {eligible_side}"
            )
    judgments_dir = run_dir / "blind" / "judgments"
    path = judgments_dir / case_id
    if path.exists():
        raise ValueError(f"judgment is immutable and already recorded: {case_id}")
    staging = Path(tempfile.mkdtemp(prefix=f".{case_id}-", dir=judgments_dir))
    try:
        judgment = {
            "schema_version": 2,
            "case_id": case_id,
            "choice": choice,
            "critical_failures": [
                {"side": side, "category": category}
                for side, category in critical
            ],
            "note": note,
            "recorded_at": now_iso(),
            "blind_lock_sha256": blind_lock_sha256,
        }
        atomic_write_json(staging / "judgment.json", judgment)
        atomic_write_json(
            staging / "judgment-lock.json",
            {
                "schema_version": 1,
                "blind_lock_sha256": blind_lock_sha256,
                "judgment_sha256": file_hash(staging / "judgment.json"),
            },
        )
        staging.rename(path)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def load_judgments(
    run_dir: Path,
    dataset: dict[str, Any],
    blind_lock_sha256: str,
) -> list[dict[str, Any]]:
    judgments_dir = run_dir / "blind" / "judgments"
    paths = sorted(path for path in judgments_dir.iterdir() if path.is_dir())
    expected_ids = [case["id"] for case in dataset["cases"]]
    if [path.name for path in paths] != sorted(expected_ids):
        raise ValueError("blind review judgments are incomplete or contain extras")
    rows = []
    allowed = set(dataset["critical_categories"])
    for case_id in expected_ids:
        case_dir = judgments_dir / case_id
        judgment_path = case_dir / "judgment.json"
        judgment_lock = read_json(
            case_dir / "judgment-lock.json",
            "blind judgment lock",
        )
        if (
            judgment_lock.get("schema_version") != 1
            or judgment_lock.get("blind_lock_sha256") != blind_lock_sha256
            or judgment_lock.get("judgment_sha256") != file_hash(judgment_path)
        ):
            raise ValueError(f"blind judgment lock changed: {case_id}")
        row = read_json(judgment_path, "blind judgment")
        if (
            row.get("schema_version") != 2
            or row.get("case_id") != case_id
            or row.get("choice") not in CHOICES
            or row.get("blind_lock_sha256") != blind_lock_sha256
        ):
            raise ValueError(f"blind judgment changed: {case_id}")
        failures = row.get("critical_failures")
        if not isinstance(failures, list):
            raise TypeError(f"blind judgment failures are invalid: {case_id}")
        for failure in failures:
            if (
                not isinstance(failure, dict)
                or failure.get("side") not in {"A", "B"}
                or failure.get("category") not in allowed
            ):
                raise ValueError(f"blind judgment failure changed: {case_id}")
        if not isinstance(row.get("note"), str):
            raise TypeError(f"blind judgment note is invalid: {case_id}")
        rows.append(row)
    return rows


def report_note(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def results(run_dir: Path) -> dict[str, Any]:
    results_dir = run_dir / "results"
    if results_dir.exists():
        raise ValueError("visual eval result is immutable and already written")
    run, dataset, _, key, blind_lock_sha256 = validate_blind(run_dir)
    judgments = load_judgments(run_dir, dataset, blind_lock_sha256)
    mapping = key["mapping"]
    wins = {"baseline": 0, "candidate": 0, "tie": 0}
    critical = {"baseline": [], "candidate": []}
    rows = []
    for judgment in judgments:
        case_id = judgment["case_id"]
        choice = judgment["choice"]
        winner = (
            "tie" if choice == "tie" else mapping[case_id][choice]["variant"]
        )
        wins[winner] += 1
        for failure in judgment["critical_failures"]:
            variant = mapping[case_id][failure["side"]]["variant"]
            critical[variant].append(
                {"case_id": case_id, "category": failure["category"]}
            )
        rows.append(
            {"case_id": case_id, "winner": winner, "note": judgment["note"]}
        )
    promotion = dataset["promotion"]
    passed = (
        wins["candidate"] >= promotion["minimum_candidate_wins"]
        and len(critical["candidate"])
        <= promotion["maximum_candidate_critical_failures"]
    )
    result = {
        "ok": True,
        "schema_version": 2,
        "run_id": run["run_id"],
        "labels": run["labels"],
        "backend": run["backend"],
        "wins": wins,
        "critical_failures": critical,
        "promotion_passed": passed,
        "verdict": "promote_candidate" if passed else "keep_baseline",
        "blind_lock_sha256": blind_lock_sha256,
        "cases": rows,
    }
    report = [
        "# Three-case visual A/B result",
        "",
        f"- Baseline: `{run['labels']['baseline']}`",
        f"- Candidate: `{run['labels']['candidate']}`",
        f"- Backend: `{run['backend']}`",
        f"- Candidate wins: {wins['candidate']}/3",
        f"- Baseline wins: {wins['baseline']}/3",
        f"- Ties: {wins['tie']}/3",
        f"- Candidate critical failures: {len(critical['candidate'])}",
        f"- Verdict: `{result['verdict']}`",
        "",
        "| Case | Winner | Note |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        report.append(
            f"| {row['case_id']} | {row['winner']} | {report_note(row['note'])} |"
        )
    staging = Path(tempfile.mkdtemp(prefix=".results-", dir=run_dir))
    try:
        atomic_write_text(staging / "REPORT.md", "\n".join(report) + "\n")
        atomic_write_json(staging / "result.json", result)
        staging.rename(results_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result


def parse_critical(value: str) -> tuple[str, str]:
    side, separator, category = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("critical must look like A=identity")
    return side, category


def parse_feedback_failure(value: str) -> tuple[str, str, str]:
    case_id, separator, remainder = value.partition("=")
    variant, variant_separator, category = remainder.partition(":")
    if not separator or not variant_separator:
        raise argparse.ArgumentTypeError(
            "feedback failure must look like CASE_ID=candidate:manga_medium"
        )
    return case_id, variant, category


def record_human_feedback(
    run_dir: Path,
    failures: list[tuple[str, str, str]],
    note: str,
) -> dict[str, Any]:
    result_path = run_dir / "results" / "result.json"
    read_json(result_path, "immutable visual eval result")
    dataset = read_json(run_dir / "dataset.json", "visual eval dataset snapshot")
    case_ids = {case["id"] for case in dataset.get("cases", [])}
    allowed = set(dataset.get("critical_categories", []))
    if not failures:
        raise ValueError("explicit human feedback requires at least one critical failure")
    normalized = []
    for case_id, variant, category in failures:
        if case_id not in case_ids:
            raise ValueError(f"unknown feedback case: {case_id}")
        if variant not in VARIANTS:
            raise ValueError(f"feedback variant must be one of {VARIANTS}")
        if category not in allowed:
            raise ValueError(f"unknown feedback critical category: {category}")
        normalized.append(
            {"case_id": case_id, "variant": variant, "category": category}
        )
    recorded_at = now_iso()
    event_core = {
        "schema_version": 1,
        "source": "explicit-user-feedback",
        "recorded_at": recorded_at,
        "result_sha256": file_hash(result_path),
        "critical_failures": normalized,
        "note": note,
    }
    event = {**event_core, "event_id": json_hash(event_core)}
    path = run_dir / "human-feedback.jsonl"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    for line in existing.splitlines():
        current = json.loads(line)
        if current.get("event_id") == event["event_id"]:
            raise ValueError("human feedback event is already recorded")
    atomic_write_text(
        path,
        existing + json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
    )
    effective = effective_results(run_dir)
    return {
        "ok": True,
        "event_id": event["event_id"],
        "effective_verdict": effective["verdict"],
        "promotion_passed": effective["promotion_passed"],
    }


def effective_results(run_dir: Path) -> dict[str, Any]:
    result_path = run_dir / "results" / "result.json"
    result = read_json(result_path, "immutable visual eval result")
    dataset = read_json(run_dir / "dataset.json", "visual eval dataset snapshot")
    result_sha256 = file_hash(result_path)
    case_ids = {case["id"] for case in dataset.get("cases", [])}
    allowed = set(dataset.get("critical_categories", []))
    human_critical = {"baseline": [], "candidate": []}
    events = []
    feedback_path = run_dir / "human-feedback.jsonl"
    if feedback_path.is_file():
        for number, line in enumerate(
            feedback_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid human feedback line {number}: {exc}") from exc
            if event.get("schema_version") != 1:
                raise ValueError(f"invalid human feedback schema on line {number}")
            if event.get("result_sha256") != result_sha256:
                raise ValueError(f"human feedback result lock changed on line {number}")
            failures = event.get("critical_failures")
            if not isinstance(failures, list):
                raise TypeError(f"invalid human feedback failures on line {number}")
            for failure in failures:
                case_id = failure.get("case_id")
                variant = failure.get("variant")
                category = failure.get("category")
                if (
                    case_id not in case_ids
                    or variant not in VARIANTS
                    or category not in allowed
                ):
                    raise ValueError(f"invalid human feedback failure on line {number}")
                human_critical[variant].append(
                    {"case_id": case_id, "category": category}
                )
            events.append(event)
    merged_critical = {
        variant: [
            *result.get("critical_failures", {}).get(variant, []),
            *human_critical[variant],
        ]
        for variant in VARIANTS
    }
    promotion = dataset["promotion"]
    passed = (
        result.get("wins", {}).get("candidate", 0)
        >= promotion["minimum_candidate_wins"]
        and len(merged_critical["candidate"])
        <= promotion["maximum_candidate_critical_failures"]
    )
    return {
        **result,
        "source_result_sha256": result_sha256,
        "human_feedback_events": len(events),
        "critical_failures": merged_critical,
        "promotion_passed": passed,
        "verdict": "promote_candidate" if passed else "keep_baseline",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in (
        "check",
        "prepare",
        "record",
        "blind",
        "judge",
        "results",
        "record-human-feedback",
        "effective-results",
    ):
        mode.add_argument(f"--{name}", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--baseline-label")
    parser.add_argument("--candidate-label")
    parser.add_argument("--backend")
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--case-id")
    parser.add_argument("--task-dir", type=Path)
    parser.add_argument("--attempt-dir", type=Path)
    parser.add_argument("--choice", choices=CHOICES)
    parser.add_argument("--critical", action="append", type=parse_critical, default=[])
    parser.add_argument(
        "--feedback-failure",
        action="append",
        type=parse_feedback_failure,
        default=[],
    )
    parser.add_argument("--note", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def require(args: argparse.Namespace, *names: str) -> None:
    missing = [name for name in names if getattr(args, name) in (None, "")]
    if missing:
        raise ValueError(f"missing required arguments: {', '.join(missing)}")


def main() -> int:
    args = parse_args()
    dataset_path = args.dataset.expanduser().resolve()
    if args.check:
        dataset = load_dataset(dataset_path)
        result = {
            "ok": True,
            "dataset": str(dataset_path),
            "cases": len(dataset["cases"]),
            "images": dataset["policy"]["total_images"],
        }
    elif args.prepare:
        require(args, "run_id", "baseline_label", "candidate_label", "backend")
        root = workflow_root(load_config(), args.workflow_root)
        run_dir = prepare_run(
            dataset_path,
            root,
            args.run_id,
            args.baseline_label,
            args.candidate_label,
            args.backend,
        )
        result = {"ok": True, "run_dir": str(run_dir), "required_images": 6}
    else:
        require(args, "run_dir")
        run_dir = args.run_dir.expanduser().resolve()
        if args.record:
            require(args, "variant", "case_id", "task_dir", "attempt_dir")
            slot = record_slot(
                run_dir,
                args.variant,
                args.case_id,
                args.task_dir,
                args.attempt_dir,
            )
            result = {"ok": True, "slot": str(slot)}
        elif args.blind:
            result = {"ok": True, "review_dir": str(blind_run(run_dir))}
        elif args.judge:
            require(args, "case_id", "choice")
            judge_run(run_dir, args.case_id, args.choice, args.critical, args.note)
            result = {"ok": True, "case_id": args.case_id, "choice": args.choice}
        elif args.record_human_feedback:
            result = record_human_feedback(
                run_dir, args.feedback_failure, args.note
            )
        elif args.effective_results:
            result = effective_results(run_dir)
        else:
            result = results(run_dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
