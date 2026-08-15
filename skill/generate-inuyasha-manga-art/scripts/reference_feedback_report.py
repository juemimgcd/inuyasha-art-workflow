#!/usr/bin/env python3
"""Summarize accepted/rejected attempt evidence for reference selection."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median

from task_workflow import (
    DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS,
    DEFAULT_POST_GENERATION_TARGET_SECONDS,
    read_json,
    reference_performance,
    task_intent,
)
from technical_failures import is_network_failure, transport_retry_exhausted
from workflow_common import load_config, workflow_paths, workflow_root


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * fraction) - 1e-9)))
    return ordered[index]


def duration_summary(values: list[float]) -> dict:
    return {
        "recorded": len(values),
        "average_seconds": round(mean(values), 1) if values else None,
        "median_seconds": round(median(values), 1) if values else None,
        "p90_seconds": round(percentile(values, 0.9), 1) if values else None,
        "maximum_seconds": round(max(values), 1) if values else None,
    }


def byte_summary(values: list[float]) -> dict:
    return {
        "recorded": len(values),
        "average_bytes": round(mean(values), 1) if values else None,
        "median_bytes": round(median(values), 1) if values else None,
        "p90_bytes": round(percentile(values, 0.9), 1) if values else None,
        "maximum_bytes": round(max(values), 1) if values else None,
    }


def seconds_text(value: float | None) -> str:
    return "n/a" if value is None else f"{value}s"


def ratio_text(value: float | None) -> str:
    return "n/a" if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    tasks_root = workflow_paths(root)["tasks"]
    performance = reference_performance(tasks_root)
    failures = Counter()
    statuses = Counter()
    error_tasks = Counter()
    durations: list[float] = []
    durations_by_intent: dict[str, list[float]] = {
        "new": [],
        "edit": [],
        "microfix": [],
    }
    response_durations: list[float] = []
    response_durations_by_intent: dict[str, list[float]] = {
        "new": [],
        "edit": [],
        "microfix": [],
    }
    response_slo_met = 0
    response_eligible = 0
    pre_generation_durations: list[float] = []
    post_generation_durations: list[float] = []
    overhead_durations: list[float] = []
    pre_generation_met = 0
    post_generation_met = 0
    reference_counts: list[int] = []
    tracked_submissions = 0
    untracked_remote_attempts = 0
    exhausted_network_errors = 0
    input_bytes: list[float] = []
    semantic_attempts = Counter()
    semantic_network_errors = Counter()
    for path in tasks_root.glob("*/attempts/*/attempt.json"):
        task_dir = path.parents[2]
        if (task_dir / "archived.json").is_file():
            continue
        attempt = read_json(path)
        brief_path = task_dir / "brief.json"
        brief = read_json(brief_path) if brief_path.is_file() else {}
        intent = task_intent(brief)
        status = attempt.get("status", "unknown")
        statuses[status] += 1
        if status == "error":
            error_tasks[path.parents[2].name] += 1
        actual_inputs = attempt.get("actual_input_images") or []
        has_submission = bool(attempt.get("generation_submission_sha256"))
        if has_submission:
            tracked_submissions += 1
        generator = str(attempt.get("generator", "")).lower()
        is_remote_attempt = (
            "image" in generator
            and isinstance(attempt.get("duration_seconds"), (int, float))
            and float(attempt["duration_seconds"]) >= 5
        ) or status == "error"
        if is_remote_attempt and not has_submission:
            untracked_remote_attempts += 1
        payload = attempt.get("actual_input_bytes")
        if isinstance(payload, (int, float)) and payload >= 0:
            input_bytes.append(float(payload))
        semantic_intent = (
            "edit"
            if any(item.get("role") == "target" for item in actual_inputs)
            else intent
        )
        semantic_attempts[semantic_intent] += 1
        if is_network_failure(attempt):
            semantic_network_errors[semantic_intent] += 1
        if transport_retry_exhausted(attempt):
            exhausted_network_errors += 1
        duration = attempt.get("duration_seconds")
        if isinstance(duration, (int, float)) and duration >= 0:
            durations.append(float(duration))
            durations_by_intent.setdefault(intent, []).append(float(duration))
        if status in {"accepted", "rejected"} and attempt.get("output"):
            response_eligible += 1
            response_duration = attempt.get("response_seconds")
            if isinstance(response_duration, (int, float)) and response_duration >= 0:
                response_value = float(response_duration)
                slo_seconds = attempt.get("response_slo_seconds")
                if isinstance(slo_seconds, (int, float)):
                    response_durations.append(response_value)
                    response_durations_by_intent.setdefault(intent, []).append(
                        response_value
                    )
                    if response_value <= slo_seconds:
                        response_slo_met += 1
            pre_generation = attempt.get("pre_generation_seconds")
            if isinstance(pre_generation, (int, float)) and pre_generation >= 0:
                pre_generation_durations.append(float(pre_generation))
                if attempt.get("pre_generation_target_met") is True:
                    pre_generation_met += 1
            post_generation = attempt.get("post_generation_seconds")
            if isinstance(post_generation, (int, float)) and post_generation >= 0:
                post_generation_durations.append(float(post_generation))
                if attempt.get("post_generation_target_met") is True:
                    post_generation_met += 1
            overhead = attempt.get("workflow_overhead_seconds")
            if isinstance(overhead, (int, float)) and overhead >= 0:
                overhead_durations.append(float(overhead))
        reference_counts.append(len(attempt.get("reference_item_ids") or []))
        for failure in attempt.get("failures", []):
            failures[failure.get("category", "unknown")] += 1
    total_attempts = sum(statuses.values())
    result = {
        "total_attempts": total_attempts,
        "accepted_attempts": statuses["accepted"],
        "rejected_attempts": statuses["rejected"],
        "error_attempts": statuses["error"],
        "accepted_yield": (
            round(statuses["accepted"] / total_attempts, 4) if total_attempts else 0.0
        ),
        "duration_coverage": {
            **duration_summary(durations),
            "total": total_attempts,
            "by_intent": {
                intent: duration_summary(values)
                for intent, values in durations_by_intent.items()
            },
        },
        "response_slo": {
            "policy": "legacy-only",
            "eligible_previews": response_eligible,
            **duration_summary(response_durations),
            "compliance_rate": (
                round(response_slo_met / len(response_durations), 4)
                if response_durations
                else None
            ),
            "by_intent": {
                intent: duration_summary(values)
                for intent, values in response_durations_by_intent.items()
            },
        },
        "workflow_overhead": {
            "generation_latency_policy": "observe-only",
            "pre_generation": {
                "default_target_seconds": DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS,
                **duration_summary(pre_generation_durations),
                "compliance_rate": (
                    round(pre_generation_met / len(pre_generation_durations), 4)
                    if pre_generation_durations
                    else None
                ),
            },
            "post_generation": {
                "default_target_seconds": DEFAULT_POST_GENERATION_TARGET_SECONDS,
                **duration_summary(post_generation_durations),
                "compliance_rate": (
                    round(post_generation_met / len(post_generation_durations), 4)
                    if post_generation_durations
                    else None
                ),
            },
            "combined": duration_summary(overhead_durations),
        },
        "average_reference_count": (
            round(sum(reference_counts) / len(reference_counts), 2)
            if reference_counts
            else 0.0
        ),
        "generation_transport": {
            "tracked_submissions": tracked_submissions,
            "untracked_remote_attempts": untracked_remote_attempts,
            "transport_retry_exhausted_errors": exhausted_network_errors,
            "actual_input_bytes": byte_summary(input_bytes),
            "by_semantic_intent": {
                intent_name: {
                    "attempts": semantic_attempts[intent_name],
                    "network_errors": semantic_network_errors[intent_name],
                    "network_error_rate": (
                        round(
                            semantic_network_errors[intent_name]
                            / semantic_attempts[intent_name],
                            4,
                        )
                        if semantic_attempts[intent_name]
                        else 0.0
                    ),
                }
                for intent_name in sorted(semantic_attempts)
            },
        },
        "repeated_error_tasks": dict(
            sorted(
                (
                    (task_id, count)
                    for task_id, count in error_tasks.items()
                    if count >= 2
                ),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "failure_categories": dict(failures.most_common()),
        "references": dict(
            sorted(
                performance.items(),
                key=lambda item: (
                    -item[1]["total"],
                    -item[1]["smoothed_acceptance"],
                    item[0],
                ),
            )
        ),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(
        "Attempts: "
        f"total={total_attempts} accepted={statuses['accepted']} "
        f"rejected={statuses['rejected']} error={statuses['error']}"
    )
    print(
        "Measured generation duration: "
        f"{len(durations)}/{total_attempts}; "
        f"median={result['duration_coverage']['median_seconds']}s; "
        f"max={result['duration_coverage']['maximum_seconds']}s"
    )
    print(
        "Legacy total-response SLO (historical attempts only): "
        f"recorded={len(response_durations)}/{response_eligible}; "
        f"average={seconds_text(result['response_slo']['average_seconds'])}; "
        f"median={seconds_text(result['response_slo']['median_seconds'])}; "
        f"p90={seconds_text(result['response_slo']['p90_seconds'])}; "
        f"compliance={ratio_text(result['response_slo']['compliance_rate'])}"
    )
    for intent, summary in result["response_slo"]["by_intent"].items():
        print(
            f"  {intent}: recorded={summary['recorded']} "
            f"average={seconds_text(summary['average_seconds'])} "
            f"median={seconds_text(summary['median_seconds'])} "
            f"p90={seconds_text(summary['p90_seconds'])}"
        )
    pre_summary = result["workflow_overhead"]["pre_generation"]
    post_summary = result["workflow_overhead"]["post_generation"]
    combined_summary = result["workflow_overhead"]["combined"]
    print(
        "Controllable pre-generation overhead: "
        f"recorded={pre_summary['recorded']} "
        f"median={seconds_text(pre_summary['median_seconds'])} "
        f"p90={seconds_text(pre_summary['p90_seconds'])} "
        f"compliance={ratio_text(pre_summary['compliance_rate'])}"
    )
    print(
        "Controllable post-generation overhead: "
        f"recorded={post_summary['recorded']} "
        f"median={seconds_text(post_summary['median_seconds'])} "
        f"p90={seconds_text(post_summary['p90_seconds'])} "
        f"compliance={ratio_text(post_summary['compliance_rate'])}"
    )
    print(
        "Combined controllable overhead: "
        f"median={seconds_text(combined_summary['median_seconds'])} "
        f"p90={seconds_text(combined_summary['p90_seconds'])}"
    )
    print(f"Average references per attempt: {result['average_reference_count']}")
    transport = result["generation_transport"]
    print(
        "Generation submission tracking: "
        f"tracked={transport['tracked_submissions']} "
        f"untracked_remote={transport['untracked_remote_attempts']} "
        f"transport_exhausted={transport['transport_retry_exhausted_errors']}"
    )
    if result["repeated_error_tasks"]:
        print(
            "Retry-stop violations: "
            + ", ".join(
                f"{task_id}={count} errors"
                for task_id, count in result["repeated_error_tasks"].items()
            )
        )
    print(
        "Failure categories: "
        + (
            ", ".join(f"{key}={value}" for key, value in failures.most_common())
            or "none"
        )
    )
    for item_id, stats in result["references"].items():
        print(
            f"{item_id}: accepted={stats['accepted']} rejected={stats['rejected']} "
            f"smoothed={stats['smoothed_acceptance']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
