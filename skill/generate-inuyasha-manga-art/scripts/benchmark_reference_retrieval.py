#!/usr/bin/env python3
"""Measure Top-K retrieval quality against a small curated intent benchmark."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from workflow_common import (
    eligible_character_style_candidate,
    load_config,
    workflow_root,
)

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = SKILL_DIR / "references" / "retrieval-benchmark.json"
SEARCH_SCRIPT = Path(__file__).resolve().with_name("search_reference_index.py")
BROWSE_SCRIPT = Path(__file__).resolve().with_name("browse_curated_styles.py")
SUPPORTED_TOOLS = {"search_reference_index", "browse_curated_styles"}
REPEATABLE_FLAGS = {
    "subject_form": "--subject-form",
    "subject": "--subject",
    "form": "--form",
    "shot": "--shot",
    "folder": "--folder",
    "content": "--content",
    "prefer_subject_form": "--prefer-subject-form",
}
SCALAR_FLAGS = {
    "source": "--source",
    "reference_domain": "--reference-domain",
    "medium": "--medium",
    "role": "--role",
    "kind": "--kind",
    "query": "--query",
    "match": "--match",
    "view_angle": "--view-angle",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--k", type=int, action="append", default=[])
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum returned candidates used to calculate reciprocal rank.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when dataset thresholds are not met.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("retrieval benchmark schema_version must be 1")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrieval benchmark requires at least one case")
    seen_ids: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("every benchmark case requires a non-empty id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate benchmark case id: {case_id}")
        seen_ids.add(case_id)
        if not str(case.get("intent_text", "")).strip():
            raise ValueError(f"benchmark case {case_id} requires intent_text")
        relevant = case.get("relevant_item_ids")
        if not isinstance(relevant, list) or not relevant:
            raise ValueError(f"benchmark case {case_id} requires relevant_item_ids")
        if not isinstance(case.get("query"), dict):
            raise TypeError(f"benchmark case {case_id} requires query")
        query = case["query"]
        tool = case.get("tool", "search_reference_index")
        if tool not in SUPPORTED_TOOLS:
            raise ValueError(f"benchmark case {case_id} uses unknown tool: {tool}")
        strict_pairs = case.get("strict_subject_forms", [])
        if not isinstance(strict_pairs, list) or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(value, str) and value for value in pair)
            for pair in strict_pairs
        ):
            raise ValueError(
                f"benchmark case {case_id} strict_subject_forms must contain [subject, form] pairs"
            )
        if (
            query.get("reference_domain") == "character-style"
            and query.get("role") == "rendering"
        ):
            requested_pair_values = query.get("prefer_subject_form") or query.get(
                "subject_form"
            )
            if not isinstance(requested_pair_values, list) or not requested_pair_values:
                raise ValueError(
                    f"benchmark case {case_id} character-style rendering requires "
                    "exact requested character-form pairs"
                )
            requested_pairs = {
                tuple(value.split("=", 1))
                for value in requested_pair_values
                if isinstance(value, str) and "=" in value
            }
            if requested_pairs != {tuple(pair) for pair in strict_pairs}:
                raise ValueError(
                    f"benchmark case {case_id} strict_subject_forms must exactly "
                    "match its requested character-form pairs"
                )
    return data


def first_relevant_rank(
    returned_item_ids: list[str], relevant_item_ids: set[str]
) -> int | None:
    for rank, item_id in enumerate(returned_item_ids, 1):
        if item_id in relevant_item_ids:
            return rank
    return None


def metric_summary(ranks: list[int | None], ks: list[int]) -> dict[str, float]:
    total = len(ranks)
    metrics = {
        f"recall_at_{k}": round(
            sum(rank is not None and rank <= k for rank in ranks) / total, 4
        )
        for k in ks
    }
    metrics["mrr"] = round(
        sum(1 / rank for rank in ranks if rank is not None) / total, 4
    )
    return metrics


def search_command(case: dict[str, Any], root: Path, limit: int) -> list[str]:
    tool = case.get("tool", "search_reference_index")
    script = BROWSE_SCRIPT if tool == "browse_curated_styles" else SEARCH_SCRIPT
    command = [
        sys.executable,
        str(script),
        "--workflow-root",
        str(root),
        "--intent-text",
        case["intent_text"],
        "--limit",
        str(limit),
        "--json",
    ]
    query = case["query"]
    for key, flag in SCALAR_FLAGS.items():
        value = query.get(key)
        if value not in (None, ""):
            command.extend([flag, str(value)])
    for key, flag in REPEATABLE_FLAGS.items():
        if key == "prefer_subject_form" and tool != "browse_curated_styles":
            continue
        for value in query.get(key, []):
            command.extend([flag, str(value)])
    return command


def run_case(case: dict[str, Any], root: Path, limit: int) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        search_command(case, root, limit),
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if completed.returncode not in (0, 1):
        raise RuntimeError(
            completed.stderr.strip() or completed.stdout.strip() or case["id"]
        )
    payload = json.loads(completed.stdout or "[]")
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else payload
    returned_ids = [candidate["item_id"] for candidate in candidates]
    relevant_ids = set(case["relevant_item_ids"])
    rank = first_relevant_rank(returned_ids, relevant_ids)
    strict_pairs = [tuple(pair) for pair in case.get("strict_subject_forms", [])]
    strict_violations = [
        candidate["item_id"]
        for candidate in candidates
        if strict_pairs
        and not eligible_character_style_candidate(candidate, strict_pairs)
    ]
    return {
        "id": case["id"],
        "intent_text": case["intent_text"],
        "relevant_item_ids": case["relevant_item_ids"],
        "rank": rank,
        "top_item_ids": returned_ids,
        "strict_subject_forms": case.get("strict_subject_forms", []),
        "strict_violations": strict_violations,
        "inferred_traits": (
            candidates[0].get("inferred_traits", []) if candidates else []
        ),
        "latency_ms": elapsed_ms,
    }


def main() -> int:
    args = parse_args()
    ks = sorted(set(args.k or [1, 3]))
    if any(k < 1 for k in ks):
        raise SystemExit("--k values must be positive")
    if args.limit < max(ks) or args.limit > 200:
        raise SystemExit("--limit must be at least max(k) and no greater than 200")
    dataset = load_dataset(args.dataset)
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    cases = [run_case(case, root, args.limit) for case in dataset["cases"]]
    metrics = metric_summary([case["rank"] for case in cases], ks)
    metrics["mean_latency_ms"] = round(
        sum(case["latency_ms"] for case in cases) / len(cases), 2
    )
    thresholds = dataset.get("thresholds", {})
    failures = [
        f"{name}={metrics.get(name, 0):.4f} below {minimum:.4f}"
        for name, minimum in thresholds.items()
        if metrics.get(name, 0) < minimum
    ]
    failures.extend(
        f"{case['id']} returned ineligible character/form items: {case['strict_violations']}"
        for case in cases
        if case["strict_violations"]
    )
    result = {
        "ok": not failures,
        "dataset": str(args.dataset.expanduser().resolve()),
        "workflow_root": str(root),
        "case_count": len(cases),
        "metrics": metrics,
        "thresholds": thresholds,
        "failures": failures,
        "cases": cases,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            " ".join(
                [f"cases={len(cases)}"]
                + [f"{name}={value}" for name, value in metrics.items()]
            )
        )
        for case in cases:
            print(f"{case['id']}: rank={case['rank']} top={case['top_item_ids'][:3]}")
        for failure in failures:
            print(f"FAIL: {failure}")
    return 2 if args.check and failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
