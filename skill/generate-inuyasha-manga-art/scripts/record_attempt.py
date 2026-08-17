#!/usr/bin/env python3
"""Record one immutable generation attempt and its exact submitted prompt."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from preference_profile import write_profile
from task_workflow import (
    ATTEMPT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    elapsed_seconds,
    is_split_domain_task,
    latency_budget,
    parse_timestamp,
    qa_acceptance_failures,
    read_json,
    reference_strategy_failures,
)
from technical_failures import is_network_failure, transport_retry_exhausted
from workflow_common import atomic_write_json, now_iso

PREVIEW_CHECK_CATEGORIES = ("identity", "request", "medium", "technical")
PREVIEW_CHECK_RESULTS = {"pass", "warning", "fail"}
MEDIUM_COMPONENT_RESULTS = {"pass", "warning", "fail", "n/a"}
MANGA_MEDIUM_COMPONENTS = (
    "face-hair",
    "fabric-fold",
    "scene-material",
    "value-hierarchy",
)


def parse_failure(value: str) -> dict[str, str]:
    category, separator, note = value.partition("=")
    if not separator or not category.strip() or not note.strip():
        raise argparse.ArgumentTypeError("failure must look like CATEGORY=NOTE")
    return {"category": category.strip(), "note": note.strip()}


def parse_preview_check(value: str) -> dict[str, str]:
    category, separator, remainder = value.partition("=")
    result, note_separator, note = remainder.partition(":")
    category = category.strip()
    result = result.strip().casefold()
    if not separator or category not in PREVIEW_CHECK_CATEGORIES:
        allowed = ", ".join(PREVIEW_CHECK_CATEGORIES)
        raise argparse.ArgumentTypeError(
            f"preview check must use one of {allowed}: CATEGORY=pass|warning|fail:NOTE"
        )
    if result not in PREVIEW_CHECK_RESULTS:
        raise argparse.ArgumentTypeError(
            "preview check result must be pass, warning, or fail"
        )
    if not note_separator or not note.strip():
        raise argparse.ArgumentTypeError(
            "preview check must include concrete visual evidence after ':'"
        )
    return {"category": category, "result": result, "note": note.strip()}


def parse_medium_component_check(value: str) -> dict[str, str]:
    component, separator, remainder = value.partition("=")
    result, note_separator, note = remainder.partition(":")
    component = component.strip()
    result = result.strip().casefold()
    if not separator or component not in MANGA_MEDIUM_COMPONENTS:
        allowed = ", ".join(MANGA_MEDIUM_COMPONENTS)
        raise argparse.ArgumentTypeError(
            f"medium component check must use one of {allowed}: COMPONENT=pass|warning|fail|n/a:NOTE"
        )
    if result not in MEDIUM_COMPONENT_RESULTS:
        raise argparse.ArgumentTypeError(
            "medium component check result must be pass, warning, fail, or n/a"
        )
    if not note_separator or not note.strip():
        raise argparse.ArgumentTypeError(
            "medium component check needs concrete visual evidence after ':'"
        )
    return {"component": component, "result": result, "note": note.strip()}


def medium_component_failures(
    status: str, checks: list[dict[str, str]], *, required: bool
) -> list[str]:
    if status != "candidate" or not required:
        return []
    components = [check.get("component", "") for check in checks]
    failures = []
    duplicates = sorted(
        component for component in set(components) if components.count(component) > 1
    )
    if duplicates:
        failures.append("duplicate manga medium components: " + ", ".join(duplicates))
    missing = [
        component for component in MANGA_MEDIUM_COMPONENTS if component not in components
    ]
    if missing:
        failures.append("missing manga medium components: " + ", ".join(missing))
    failed = [
        check.get("component", "")
        for check in checks
        if check.get("result") == "fail"
    ]
    if failed:
        failures.append("failed manga medium components: " + ", ".join(failed))
    value_checks = [
        check for check in checks if check.get("component") == "value-hierarchy"
    ]
    if value_checks and value_checks[0].get("result") == "n/a":
        failures.append("value-hierarchy cannot be n/a for a manga candidate")
    return failures


def requires_manga_medium_components(brief: dict) -> bool:
    """Apply the component gate to current split-domain manga tasks at every shot."""
    return brief.get("medium") == "manga" and bool(
        brief.get("character_style_targets")
    )


def preview_handoff_failures(
    status: str, checks: list[dict[str, str]]
) -> list[str]:
    """Return blocking first-preview defects before a candidate can be handed off."""
    categories = [check.get("category", "") for check in checks]
    failures = []
    duplicates = sorted(
        category for category in set(categories) if categories.count(category) > 1
    )
    if duplicates:
        failures.append("duplicate preview checks: " + ", ".join(duplicates))
    unknown = sorted(set(categories) - set(PREVIEW_CHECK_CATEGORIES))
    if unknown:
        failures.append("unknown preview checks: " + ", ".join(unknown))
    invalid_results = sorted(
        {
            str(check.get("result", ""))
            for check in checks
            if check.get("result") not in PREVIEW_CHECK_RESULTS
        }
    )
    if invalid_results:
        failures.append("preview checks must use pass, warning, or fail")
    missing_notes = sorted(
        check.get("category", "")
        for check in checks
        if not str(check.get("note", "")).strip()
    )
    if missing_notes:
        failures.append(
            "preview checks need concrete visual evidence: "
            + ", ".join(missing_notes)
        )
    if status == "candidate":
        missing = [
            category
            for category in PREVIEW_CHECK_CATEGORIES
            if category not in categories
        ]
        if missing:
            failures.append("missing blocking preview checks: " + ", ".join(missing))
        failed = [
            check.get("category", "")
            for check in checks
            if check.get("result") == "fail"
        ]
        if failed:
            failures.append(
                "candidate has failed blocking preview checks: " + ", ".join(failed)
            )
        misplaced_warnings = [
            check.get("category", "")
            for check in checks
            if check.get("result") == "warning" and check.get("category") != "medium"
        ]
        if misplaced_warnings:
            failures.append(
                "candidate warning is only non-blocking for medium: "
                + ", ".join(misplaced_warnings)
            )
    return failures


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument(
        "--status",
        choices=("accepted", "rejected", "candidate", "error"),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--submitted-prompt",
        type=Path,
        help=(
            "Exact text submitted to the generator. Omit only when prompt.md "
            "was submitted verbatim."
        ),
    )
    parser.add_argument("--failure", type=parse_failure, action="append", default=[])
    parser.add_argument(
        "--preview-check",
        type=parse_preview_check,
        action="append",
        default=[],
        help=(
            "Blocking first-preview check recorded as "
            "identity|request|medium|technical=pass|warning|fail:NOTE. "
            "Only medium may use a non-blocking warning."
        ),
    )
    parser.add_argument(
        "--medium-component-check",
        type=parse_medium_component_check,
        action="append",
        default=[],
        help=(
            "Required for current split-domain manga candidates at every shot size: "
            "face-hair|fabric-fold|scene-material|value-hierarchy=pass|warning|fail|n/a:NOTE. "
            "Use n/a with a visible reason when a component is outside the frame; "
            "value-hierarchy is always applicable."
        ),
    )
    parser.add_argument(
        "--reference-blame",
        action="append",
        default=[],
        help=(
            "Reference item ID directly implicated in a rejected attempt. "
            "Omit for generator, preservation, or prompt failures that should not "
            "lower reference ranking."
        ),
    )
    parser.add_argument("--feedback", default="")
    parser.add_argument("--preference-tag", action="append", default=[])
    parser.add_argument("--generator", default="built-in image_gen")
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument(
        "--persist-output",
        action="store_true",
        help="Copy the generated image into task outputs before recording it.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--response-started-at",
        help=(
            "ISO-8601 start of the current user-visible response. Defaults to "
            "response-window.json, or brief.created_at for the first attempt."
        ),
    )
    args = parser.parse_args()
    preference_profile_warning = None
    if args.duration_seconds is not None and args.duration_seconds < 0:
        raise SystemExit("--duration-seconds cannot be negative")

    task_dir = args.task_dir.expanduser().resolve()
    brief = read_json(task_dir / "brief.json")
    manifest = read_json(task_dir / "reference-manifest.json")
    output = args.output.expanduser().resolve() if args.output else None
    compiled_prompt = task_dir / "prompt.md"
    if not compiled_prompt.is_file():
        raise SystemExit(f"compiled prompt is missing: {compiled_prompt}")
    submitted_prompt = (
        args.submitted_prompt.expanduser().resolve()
        if args.submitted_prompt
        else compiled_prompt
    )
    if not submitted_prompt.is_file():
        raise SystemExit(f"submitted prompt is missing: {submitted_prompt}")
    if args.status != "error" and (output is None or not output.is_file()):
        raise SystemExit(
            "accepted/rejected/candidate attempts require an existing --output"
        )
    if args.status == "rejected" and not args.failure:
        raise SystemExit("rejected attempts require at least one --failure")
    if args.status == "candidate" and args.failure:
        raise SystemExit("candidate attempts cannot contain --failure entries")
    if args.status == "error" and not any(
        failure.get("category") == "technical" for failure in args.failure
    ):
        raise SystemExit(
            "error attempts require --failure technical=NOTE so retry limits work"
        )
    preview_failures = preview_handoff_failures(args.status, args.preview_check)
    preview_failures.extend(
        medium_component_failures(
            args.status,
            args.medium_component_check,
            required=requires_manga_medium_components(brief),
        )
    )
    if preview_failures:
        raise SystemExit("candidate handoff blocked: " + "; ".join(preview_failures))
    if args.status == "accepted":
        strategy_failures = reference_strategy_failures(brief)
        if strategy_failures:
            raise SystemExit(
                "acceptance blocked by reference strategy: "
                + "; ".join(strategy_failures)
            )
        qa_path = task_dir / "qa.json"
        qa = read_json(qa_path) if qa_path.is_file() else None
        split_domain_task = is_split_domain_task(brief, qa)
        if split_domain_task and qa is None:
            raise SystemExit("split-domain acceptance requires qa.json")
        if split_domain_task:
            qa_failures = qa_acceptance_failures(qa or {})
            if qa_failures:
                raise SystemExit(
                    "split-domain acceptance blocked by QA: "
                    + "; ".join(qa_failures)
                )

    attempts_root = task_dir / "attempts"
    attempts_root.mkdir(exist_ok=True)
    existing = sorted(
        int(path.name)
        for path in attempts_root.iterdir()
        if path.is_dir() and path.name.isdigit()
    )
    number = (existing[-1] + 1) if existing else 1
    attempt_dir = attempts_root / f"{number:03d}"
    existing_attempt_rows = [
        read_json(path) for path in sorted(attempts_root.glob("*/attempt.json"))
    ]
    output_sha256 = file_hash(output) if output else None
    decision_from_attempt = None
    if args.status in {"accepted", "rejected"} and output_sha256:
        decision_from_attempt = next(
            (
                row.get("attempt")
                for row in reversed(existing_attempt_rows)
                if row.get("status") == "candidate"
                and row.get("output_sha256") == output_sha256
            ),
            None,
        )
    accepted_from_attempt = (
        decision_from_attempt if args.status == "accepted" else None
    )
    rejected_from_attempt = (
        decision_from_attempt if args.status == "rejected" else None
    )
    counts_as_generation = decision_from_attempt is None

    references = manifest.get("references", [])
    reference_item_ids = [entry.get("item_id") for entry in references]
    blame_item_ids = sorted(set(args.reference_blame))
    unknown_blame = sorted(set(blame_item_ids) - set(reference_item_ids))
    if unknown_blame:
        raise SystemExit(
            "--reference-blame must name a manifest item ID: "
            + ", ".join(unknown_blame)
        )
    if blame_item_ids and args.status != "rejected":
        raise SystemExit("--reference-blame is valid only for rejected attempts")
    recorded_at = now_iso()
    response_window_path = task_dir / "response-window.json"
    response_window = (
        read_json(response_window_path) if response_window_path.is_file() else {}
    )
    submission_path = task_dir / "generation-submission.json"
    submission = read_json(submission_path) if submission_path.is_file() else None
    if (
        int(brief.get("schema_version") or 0) >= 5
        and response_window.get("phase") == "generation"
        and (submission is None or submission.get("state") != "submitted")
    ):
        raise SystemExit(
            "a schema-5 generation attempt requires a submitted "
            "generation-submission.json snapshot"
        )
    if submission is not None:
        if submission.get("prompt_sha256") != file_hash(submitted_prompt):
            raise SystemExit(
                "recorded submitted prompt differs from generation-submission.json"
            )
        if submission.get("response_started_at") != (
            response_window.get("pre_generation_started_at")
            or response_window.get("started_at")
        ):
            raise SystemExit("generation submission belongs to another response window")
    response_started_at = (
        args.response_started_at
        or response_window.get("started_at")
        or (brief.get("created_at") if number == 1 else None)
    )
    response_seconds = None
    if response_started_at:
        try:
            parse_timestamp(response_started_at)
            response_seconds = elapsed_seconds(response_started_at, recorded_at)
        except ValueError as exc:
            raise SystemExit(f"invalid response start timestamp: {exc}") from exc
    budget = latency_budget(brief)
    generation_started_at = response_window.get("generation_started_at")
    pre_generation_seconds = response_window.get("pre_generation_seconds")
    if pre_generation_seconds is None and response_started_at and generation_started_at:
        try:
            pre_generation_seconds = elapsed_seconds(
                response_started_at, generation_started_at
            )
        except ValueError as exc:
            raise SystemExit(f"invalid generation start timestamp: {exc}") from exc
    generation_seconds = args.duration_seconds
    post_generation_seconds = None
    if (
        response_seconds is not None
        and isinstance(pre_generation_seconds, (int, float))
        and generation_seconds is not None
    ):
        post_generation_seconds = round(
            max(0.0, response_seconds - pre_generation_seconds - generation_seconds),
            1,
        )
    workflow_overhead_seconds = None
    if isinstance(pre_generation_seconds, (int, float)):
        workflow_overhead_seconds = float(pre_generation_seconds)
        if post_generation_seconds is not None:
            workflow_overhead_seconds = round(
                workflow_overhead_seconds + post_generation_seconds, 1
            )
    pre_target = int(
        response_window.get("pre_generation_target_seconds")
        or budget["pre_generation_target_seconds"]
    )
    post_target = int(
        response_window.get("post_generation_target_seconds")
        or budget["post_generation_target_seconds"]
    )
    legacy_slo = response_window.get("response_slo_seconds")
    if output is not None and args.persist_output:
        outputs_dir = task_dir / "outputs"
        outputs_dir.mkdir(exist_ok=True)
        suffix = output.suffix.lower() or ".png"
        persisted_output = outputs_dir / f"{args.status}-{number:03d}{suffix}"
        if persisted_output.exists():
            raise SystemExit(f"persisted output already exists: {persisted_output}")
        if output != persisted_output:
            shutil.copy2(output, persisted_output)
            output = persisted_output
    attempt_dir.mkdir()
    attempt = {
        "schema_version": ATTEMPT_SCHEMA_VERSION,
        "attempt": number,
        "recorded_at": recorded_at,
        "status": args.status,
        "generator": args.generator,
        "duration_seconds": args.duration_seconds,
        "generation_seconds": generation_seconds,
        "response_started_at": response_started_at,
        "response_seconds": response_seconds,
        "pre_generation_seconds": pre_generation_seconds,
        "pre_generation_target_seconds": pre_target,
        "pre_generation_target_met": (
            pre_generation_seconds <= pre_target
            if isinstance(pre_generation_seconds, (int, float))
            else None
        ),
        "post_generation_seconds": post_generation_seconds,
        "post_generation_target_seconds": post_target,
        "post_generation_target_met": (
            post_generation_seconds <= post_target
            if post_generation_seconds is not None
            else None
        ),
        "workflow_overhead_seconds": workflow_overhead_seconds,
        "response_slo_seconds": legacy_slo,
        "response_slo_met": (
            response_seconds <= legacy_slo
            if response_seconds is not None and legacy_slo is not None
            else None
        ),
        "output": str(output) if output else None,
        "output_sha256": file_hash(output) if output else None,
        "decision_from_attempt": decision_from_attempt,
        "accepted_from_attempt": accepted_from_attempt,
        "rejected_from_attempt": rejected_from_attempt,
        "counts_as_generation": counts_as_generation,
        "brief_sha256": file_hash(task_dir / "brief.json"),
        "reference_manifest_sha256": file_hash(
            task_dir / "reference-manifest.json"
        ),
        "compiled_prompt_sha256": file_hash(compiled_prompt),
        "submitted_prompt_sha256": file_hash(submitted_prompt),
        "submitted_prompt_source": (
            "explicit" if args.submitted_prompt else "compiled-verbatim"
        ),
        "submitted_prompt_differs_from_compiled": (
            file_hash(submitted_prompt) != file_hash(compiled_prompt)
        ),
        "reference_item_ids": reference_item_ids,
        "reference_blame_item_ids": blame_item_ids,
        "failures": args.failure,
        "preview_checks": args.preview_check,
        "medium_component_checks": args.medium_component_check,
        "user_feedback": args.feedback,
        "preference_tags": sorted(set(args.preference_tag)),
        "generation_submission_sha256": (
            file_hash(submission_path) if submission is not None else None
        ),
        "generation_endpoint": (
            submission.get("endpoint") if submission is not None else None
        ),
        "generation_transport": (
            submission.get("transport") if submission is not None else None
        ),
        "actual_input_bytes": (
            submission.get("input_bytes") if submission is not None else None
        ),
        "actual_input_images": (
            submission.get("images") if submission is not None else []
        ),
    }
    attempt["network_failure"] = is_network_failure(attempt)
    attempt["transport_retry_exhausted"] = transport_retry_exhausted(attempt)
    atomic_write_json(attempt_dir / "attempt.json", attempt)
    for name in ("brief.json", "prompt.md", "reference-manifest.json", "qa.json"):
        source = task_dir / name
        if source.is_file():
            shutil.copy2(source, attempt_dir / name)
    shutil.copy2(submitted_prompt, attempt_dir / "submitted-prompt.md")
    if submission is not None:
        shutil.copy2(submission_path, attempt_dir / "generation-submission.json")
        submission.update(
            {
                "state": "recorded",
                "recorded_at": recorded_at,
                "attempt": number,
                "status": args.status,
            }
        )
        atomic_write_json(submission_path, submission)

    if response_window_path.is_file():
        response_window.update(
            {
                "phase": "recorded",
                "recorded_at": recorded_at,
                "last_attempt": number,
                "last_status": args.status,
            }
        )
        atomic_write_json(response_window_path, response_window)

    if args.feedback or args.preference_tag:
        event = {
            "schema_version": 1,
            "recorded_at": now_iso(),
            "attempt": number,
            "status": args.status,
            "feedback": args.feedback,
            "tags": sorted(set(args.preference_tag)),
        }
        with (task_dir / "preference-events.jsonl").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    if args.status == "accepted":
        attempt_rows = [
            read_json(path) for path in sorted(attempts_root.glob("*/attempt.json"))
        ]
        generation_attempts = sum(
            row.get("counts_as_generation") is not False for row in attempt_rows
        )
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "status": "accepted",
            "generated_at": now_iso(),
            "generator": args.generator,
            "accepted_attempt": number,
            "revision_required": generation_attempts > 1,
            "output": str(output),
            "medium": brief.get("medium"),
            "intent": brief.get("intent"),
            "response_seconds": response_seconds,
            "generation_seconds": generation_seconds,
            "pre_generation_seconds": pre_generation_seconds,
            "pre_generation_target_seconds": pre_target,
            "pre_generation_target_met": attempt["pre_generation_target_met"],
            "post_generation_seconds": post_generation_seconds,
            "post_generation_target_seconds": post_target,
            "post_generation_target_met": attempt["post_generation_target_met"],
            "workflow_overhead_seconds": workflow_overhead_seconds,
            "revisions": [
                {
                    "attempt": row.get("attempt"),
                    "status": row.get("status"),
                    "failures": row.get("failures", []),
                    "user_feedback": row.get("user_feedback", ""),
                }
                for row in attempt_rows
            ],
            "qa": "pass",
        }
        atomic_write_json(task_dir / "result.json", result)
        try:
            write_profile(task_dir.parent.parent)
        except (OSError, TypeError, ValueError) as exc:
            preference_profile_warning = (
                "accepted result was recorded, but the derived preference profile "
                f"could not be refreshed: {exc}"
            )

    if args.json:
        print(
            json.dumps(
                {
                    "attempt": number,
                    "status": args.status,
                    "attempt_path": str(attempt_dir / "attempt.json"),
                    "output": str(output) if output else None,
                    "handoff_ready": (
                        args.status == "candidate"
                        and not preview_handoff_failures(
                            args.status, attempt["preview_checks"]
                        )
                    ),
                    "transport_retry_exhausted": attempt[
                        "transport_retry_exhausted"
                    ],
                    "preference_profile_warning": preference_profile_warning,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(attempt_dir / "attempt.json")
        if preference_profile_warning:
            print(f"warning: {preference_profile_warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
