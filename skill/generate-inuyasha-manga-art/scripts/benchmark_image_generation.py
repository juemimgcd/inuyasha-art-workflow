#!/usr/bin/env python3
"""Inspect or score the legacy identity-card first-preview benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from task_workflow import identity_requirements
from workflow_common import (
    atomic_write_json,
    atomic_write_text,
    load_config,
    open_database,
    retrieval_traits_for,
    workflow_paths,
    workflow_root,
)

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = SKILL_DIR / "references" / "generation-benchmark.json"
SCORE_STATUSES = {"pending", "usable", "visual-fail", "technical-error"}
CHECK_STATUSES = {"pending", "pass", "fail"}


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
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_image(path: Path) -> None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    except (ImportError, OSError, ValueError) as exc:
        raise ValueError(f"invalid benchmark image: {path}: {exc}") from exc


def load_dataset(path: Path) -> dict[str, Any]:
    dataset = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if dataset.get("schema_version") != 1:
        raise ValueError("generation benchmark schema_version must be 1")
    if not str(dataset.get("id", "")).strip():
        raise ValueError("generation benchmark requires id")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("generation benchmark requires cases")
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError(f"invalid or duplicate generation case id: {case_id}")
        seen.add(case_id)
        for field in (
            "form",
            "identity_card_id",
            "style_item_id",
            "shot_type",
            "aspect_ratio",
            "scene",
        ):
            if not str(case.get(field, "")).strip():
                raise ValueError(f"generation case {case_id} requires {field}")
        checks = case.get("checks")
        required_checks = {
            "identity_form",
            "identity_features",
            "costume",
            "anatomy_contact",
            "composition",
            "manga_medium",
        }
        if not isinstance(checks, dict) or set(checks) != required_checks:
            raise ValueError(
                f"generation case {case_id} checks must be {sorted(required_checks)}"
            )
        for check_id, observations in checks.items():
            if (
                not isinstance(observations, list)
                or not observations
                or not all(
                    isinstance(value, str) and value.strip() for value in observations
                )
            ):
                raise ValueError(
                    f"generation case {case_id} check {check_id} requires observations"
                )
        for identity in case.get("additional_identity", []):
            if not all(
                str(identity.get(field, "")).strip()
                for field in ("character", "form", "item_id")
            ):
                raise ValueError(
                    f"generation case {case_id} has invalid additional_identity"
                )
    return dataset


def catalog_item(connection, item_id: str):
    return connection.execute(
        """
        SELECT items.*, sources.medium
        FROM items JOIN sources ON sources.source_id = items.source_id
        WHERE items.item_id = ? OR items.item_id = (
            SELECT item_id FROM item_aliases WHERE alias_id = ?
        )
        """,
        (item_id, item_id),
    ).fetchone()


def item_forms(row, character: str) -> set[str]:
    subject_forms = json.loads(row["subject_forms"] or "{}")
    return set(subject_forms.get(character, [])) or set(
        json.loads(row["forms"] or "[]")
    )


def validate_benchmark(
    dataset: dict[str, Any], root: Path, connection
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    cards_path = root / "identity-cards" / "manifest.json"
    if not cards_path.is_file():
        return {}, [f"identity card manifest is missing: {cards_path}"]
    cards_manifest = json.loads(cards_path.read_text(encoding="utf-8"))
    if cards_manifest.get("schema_version") != 1:
        failures.append("identity card manifest schema_version must be 1")
    cards = {card.get("id"): card for card in cards_manifest.get("cards", [])}
    for card_id, card in cards.items():
        output = root / "identity-cards" / str(card.get("output_file", ""))
        if not output.is_file():
            failures.append(f"identity card output is missing: {card_id}")
        elif file_hash(output) != card.get("output_sha256"):
            failures.append(f"identity card output hash mismatch: {card_id}")

    form_counts: Counter[str] = Counter()
    shot_types: set[str] = set()
    for case in dataset["cases"]:
        case_id = case["id"]
        form_counts[case["form"]] += 1
        shot_types.add(case["shot_type"])
        card = cards.get(case["identity_card_id"])
        if card is None:
            failures.append(
                f"generation case {case_id} uses unknown identity card: "
                f"{case['identity_card_id']}"
            )
        elif card.get("character") != "犬夜叉" or card.get("form") != case["form"]:
            failures.append(f"generation case {case_id} identity card form mismatch")
        style = catalog_item(connection, case["style_item_id"])
        if style is None:
            failures.append(
                f"generation case {case_id} has unknown style item: "
                f"{case['style_item_id']}"
            )
        else:
            roles = set(json.loads(style["eligible_roles"] or "[]"))
            if style["source_id"] != "manga-curated" or "rendering" not in roles:
                failures.append(
                    f"generation case {case_id} style item is not manga rendering evidence"
                )
            source = Path(style["path"])
            if not source.is_file() or file_hash(source) != style["content_hash"]:
                failures.append(
                    f"generation case {case_id} style source is missing or changed"
                )
        if len(case.get("additional_identity", [])) + 2 > 5:
            failures.append(f"generation case {case_id} exceeds five benchmark inputs")
        for identity in case.get("additional_identity", []):
            row = catalog_item(connection, identity["item_id"])
            if row is None:
                failures.append(
                    f"generation case {case_id} has unknown identity item: "
                    f"{identity['item_id']}"
                )
                continue
            subjects = set(json.loads(row["subjects"] or "[]"))
            roles = set(json.loads(row["eligible_roles"] or "[]"))
            if (
                row["source_id"] != "official"
                or "identity" not in roles
                or identity["character"] not in subjects
                or identity["form"] not in item_forms(row, identity["character"])
            ):
                failures.append(
                    f"generation case {case_id} has incompatible additional identity: "
                    f"{identity['item_id']}"
                )

    coverage = dataset.get("coverage_requirements", {})
    minimum_cases = int(coverage.get("minimum_cases", 0))
    if len(dataset["cases"]) < minimum_cases:
        failures.append(
            f"generation benchmark has {len(dataset['cases'])} cases; "
            f"minimum is {minimum_cases}"
        )
    for form, minimum in coverage.get("forms", {}).items():
        if form_counts[form] < minimum:
            failures.append(
                f"generation benchmark form {form} has {form_counts[form]} cases; "
                f"minimum is {minimum}"
            )
    missing_shots = set(coverage.get("shot_types", [])) - shot_types
    if missing_shots:
        failures.append(
            f"generation benchmark is missing shot coverage: {sorted(missing_shots)}"
        )
    return cards, failures


def case_prompt(dataset: dict[str, Any], case: dict[str, Any]) -> str:
    contract = dataset["prompt_contract"]
    identity_authority = contract.get("identity_authority_by_card", {}).get(
        case["identity_card_id"], contract["identity_authority"]
    )
    lines = [
        "# Fixed benchmark prompt",
        "",
        "Create exactly one new image. Do not generate variants.",
        "",
        "## Input authority",
        "",
        f"- Input 1 (style): {contract['style_authority']}",
        f"- Input 2 (identity): {identity_authority}",
    ]
    for index, identity in enumerate(case.get("additional_identity", []), 3):
        lines.append(
            f"- Input {index} (identity for {identity['character']}): "
            f"{contract['additional_identity_authority']}"
        )
    lines.extend(["", "## Scene", "", case["scene"], "", "## Requirements", ""])
    for requirement in contract["global_requirements"]:
        lines.append(f"- {requirement}")
    traits = retrieval_traits_for(
        case["scene"], case["shot_type"], medium=case.get("medium")
    )
    for requirement in identity_requirements("犬夜叉", case["form"], traits):
        lines.append(f"- {requirement}")
    for check in case["checks"].values():
        for observation in check:
            lines.append(f"- {observation}")
    lines.extend(
        [
            "",
            f"Aspect ratio: {case['aspect_ratio']}.",
            "Treat every listed requirement as observable and blocking.",
        ]
    )
    return "\n".join(lines) + "\n"


def score_template(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "case_id": case["id"],
        "status": "pending",
        "duration_seconds": None,
        "output": None,
        "output_sha256": None,
        "checks": {check_id: "pending" for check_id in case["checks"]},
        "notes": [],
    }


def prepare_run(
    dataset: dict[str, Any],
    dataset_path: Path,
    root: Path,
    cards: dict[str, Any],
    connection,
    backend: str,
    run_id: str,
) -> Path:
    run_dir = root / "generation-benchmarks" / dataset["id"] / run_id
    if run_dir.exists():
        raise ValueError(f"benchmark run already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    case_locks: dict[str, dict[str, str]] = {}
    for case in dataset["cases"]:
        case_dir = run_dir / "cases" / case["id"]
        case_dir.mkdir(parents=True)
        inputs_dir = case_dir / "inputs"
        inputs_dir.mkdir()
        style = catalog_item(connection, case["style_item_id"])
        card = cards[case["identity_card_id"]]
        inputs = [
            {
                "order": 1,
                "role": "style",
                "item_id": style["item_id"],
                "source_path": style["path"],
                "authority": "manga-rendering-only",
            },
            {
                "order": 2,
                "role": "identity",
                "card_id": card["id"],
                "source_path": str(root / "identity-cards" / card["output_file"]),
                "authority": card["authority"],
                "source_item_ids": list(
                    dict.fromkeys(panel["item_id"] for panel in card.get("panels", []))
                ),
            },
        ]
        for index, identity in enumerate(case.get("additional_identity", []), 3):
            row = catalog_item(connection, identity["item_id"])
            inputs.append(
                {
                    "order": index,
                    "role": "identity",
                    "character": identity["character"],
                    "item_id": row["item_id"],
                    "source_path": row["path"],
                    "authority": row["authority"],
                }
            )
        for item in inputs:
            source = Path(item.pop("source_path")).expanduser().resolve()
            verify_image(source)
            suffix = source.suffix.casefold() or ".img"
            snapshot = inputs_dir / f"{item['order']:02d}-{item['role']}{suffix}"
            shutil.copy2(source, snapshot)
            item["path"] = str(snapshot.relative_to(case_dir))
            item["sha256"] = file_hash(snapshot)
            item["original_path"] = str(source)
        prompt_path = case_dir / "prompt.md"
        atomic_write_text(prompt_path, case_prompt(dataset, case))
        inputs_path = case_dir / "inputs.json"
        atomic_write_json(
            inputs_path,
            {
                "schema_version": 2,
                "case_id": case["id"],
                "prompt_sha256": file_hash(prompt_path),
                "input_order": inputs,
            },
        )
        atomic_write_json(case_dir / "score.json", score_template(case))
        case_locks[case["id"]] = {
            "prompt_sha256": file_hash(prompt_path),
            "inputs_sha256": file_hash(inputs_path),
        }
    atomic_write_json(
        run_dir / "run.json",
        {
            "schema_version": 2,
            "dataset_id": dataset["id"],
            "dataset_path": str(dataset_path.resolve()),
            "dataset_sha256": file_hash(dataset_path),
            "dataset_content_sha256": json_hash(dataset),
            "backend": backend,
            "prepared_at": now_iso(),
            "single_generation_per_case": True,
            "case_ids": [case["id"] for case in dataset["cases"]],
            "case_locks": case_locks,
        },
    )
    return run_dir


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * fraction) - 1e-9)))
    return ordered[index]


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def resolve_locked_path(case_dir: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("locked benchmark path is missing")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"locked benchmark path must be relative: {value}")
    resolved = (case_dir / relative).resolve()
    try:
        resolved.relative_to(case_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"locked benchmark path escapes case directory: {value}") from exc
    return resolved


def validate_case_lock(
    case: dict[str, Any], case_dir: Path, lock: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    prompt_path = case_dir / "prompt.md"
    inputs_path = case_dir / "inputs.json"
    if not prompt_path.is_file() or file_hash(prompt_path) != lock.get("prompt_sha256"):
        failures.append(f"prompt lock mismatch: {case['id']}")
    if not inputs_path.is_file() or file_hash(inputs_path) != lock.get("inputs_sha256"):
        failures.append(f"inputs lock mismatch: {case['id']}")
        return failures
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    if inputs.get("schema_version") != 2 or inputs.get("case_id") != case["id"]:
        failures.append(f"invalid inputs manifest: {case['id']}")
        return failures
    if inputs.get("prompt_sha256") != lock.get("prompt_sha256"):
        failures.append(f"inputs prompt hash mismatch: {case['id']}")
    items = inputs.get("input_order")
    if not isinstance(items, list) or not items:
        failures.append(f"benchmark inputs are missing: {case['id']}")
        return failures
    if [item.get("order") for item in items] != list(range(1, len(items) + 1)):
        failures.append(f"benchmark input order is invalid: {case['id']}")
    for item in items:
        try:
            source = resolve_locked_path(case_dir, item.get("path"))
            if not source.is_file() or file_hash(source) != item.get("sha256"):
                raise ValueError(f"input hash mismatch: {source}")
            verify_image(source)
        except (OSError, TypeError, ValueError) as exc:
            failures.append(f"invalid locked input for {case['id']}: {exc}")
    return failures


def score_run(
    dataset: dict[str, Any], run_dir: Path, dataset_path: Path | None = None
) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    if not run_path.is_file():
        raise ValueError(f"benchmark run manifest is missing: {run_path}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("schema_version") != 2:
        raise ValueError("benchmark run schema_version must be 2")
    if run.get("dataset_id") != dataset["id"]:
        raise ValueError("benchmark run dataset id does not match")
    if run.get("dataset_content_sha256") != json_hash(dataset):
        raise ValueError("benchmark run dataset content changed after preparation")
    if dataset_path is not None and (
        not dataset_path.is_file()
        or run.get("dataset_sha256") != file_hash(dataset_path)
    ):
        raise ValueError("benchmark dataset file changed after preparation")
    case_ids = [case["id"] for case in dataset["cases"]]
    if run.get("case_ids") != case_ids:
        raise ValueError("benchmark run case list does not match dataset")
    if run.get("single_generation_per_case") is not True:
        raise ValueError("benchmark run must enforce one generation per case")
    if not str(run.get("backend", "")).strip():
        raise ValueError("benchmark run backend is missing")
    case_locks = run.get("case_locks")
    if not isinstance(case_locks, dict) or set(case_locks) != set(case_ids):
        raise ValueError("benchmark run case locks do not match dataset")
    failures: list[str] = []
    durations: list[float] = []
    statuses: Counter[str] = Counter()
    check_passes: Counter[str] = Counter()
    check_totals: Counter[str] = Counter()
    pending_cases: list[str] = []
    for case in dataset["cases"]:
        case_dir = run_dir / "cases" / case["id"]
        failures.extend(validate_case_lock(case, case_dir, case_locks[case["id"]]))
        score_path = case_dir / "score.json"
        if not score_path.is_file():
            failures.append(f"missing score: {case['id']}")
            continue
        score = json.loads(score_path.read_text(encoding="utf-8"))
        if score.get("schema_version") != 2:
            failures.append(f"score schema version mismatch: {case['id']}")
            continue
        if score.get("case_id") != case["id"]:
            failures.append(f"score case id mismatch: {case['id']}")
            continue
        status = score.get("status")
        if status not in SCORE_STATUSES:
            failures.append(f"invalid score status for {case['id']}: {status}")
            continue
        statuses[status] += 1
        if status == "pending":
            pending_cases.append(case["id"])
            continue
        duration = score.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration < 0:
            failures.append(f"completed score requires duration_seconds: {case['id']}")
        else:
            durations.append(float(duration))
        checks = score.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(case["checks"]):
            failures.append(f"score checks mismatch: {case['id']}")
            continue
        if status == "technical-error":
            if score.get("output") is not None or score.get("output_sha256") is not None:
                failures.append(f"technical error must not record output: {case['id']}")
            if any(value != "pending" for value in checks.values()):
                failures.append(f"technical error checks must stay pending: {case['id']}")
            continue
        output_value = score.get("output")
        if not isinstance(output_value, str) or not output_value.strip():
            failures.append(f"visual score requires output: {case['id']}")
        else:
            output = Path(output_value).expanduser()
            if not output.is_absolute():
                output = score_path.parent / output
            if not output.is_file():
                failures.append(f"benchmark output is missing: {output}")
            else:
                try:
                    verify_image(output)
                except ValueError as exc:
                    failures.append(str(exc))
                if score.get("output_sha256") != file_hash(output):
                    failures.append(f"benchmark output hash mismatch: {case['id']}")
        for check_id, verdict in checks.items():
            if verdict not in CHECK_STATUSES - {"pending"}:
                failures.append(
                    f"visual score has invalid {check_id} verdict: {case['id']}"
                )
                continue
            check_totals[check_id] += 1
            if verdict == "pass":
                check_passes[check_id] += 1
        has_failure = any(verdict == "fail" for verdict in checks.values())
        if status == "usable" and has_failure:
            failures.append(f"usable score contains failed checks: {case['id']}")
        if status == "visual-fail" and not has_failure:
            failures.append(f"visual-fail score has no failed checks: {case['id']}")

    total = len(dataset["cases"])
    visual_total = statuses["usable"] + statuses["visual-fail"]
    metrics: dict[str, float | int | None] = {
        "case_count": total,
        "completed_cases": total - len(pending_cases),
        "technical_success_rate": rate(visual_total, total),
        "first_pass_usable_rate": rate(statuses["usable"], total),
        "median_generation_seconds": round(median(durations), 1) if durations else None,
        "p90_generation_seconds": round(percentile(durations, 0.9), 1)
        if durations
        else None,
    }
    for check_id in (
        "identity_form",
        "identity_features",
        "costume",
        "anatomy_contact",
        "composition",
        "manga_medium",
    ):
        metrics[f"{check_id}_pass_rate"] = rate(
            check_passes[check_id], check_totals[check_id]
        )
    if pending_cases:
        failures.append(f"benchmark run has pending cases: {pending_cases}")
    thresholds = dataset.get("thresholds", {})
    for name, minimum in thresholds.get("minimum", {}).items():
        value = metrics.get(name)
        if value is None or value < minimum:
            failures.append(f"{name}={value} below minimum {minimum}")
    for name, maximum in thresholds.get("maximum", {}).items():
        value = metrics.get(name)
        if value is None or value > maximum:
            failures.append(f"{name}={value} above maximum {maximum}")
    return {
        "ok": not failures,
        "run_dir": str(run_dir.resolve()),
        "backend": run.get("backend"),
        "statuses": dict(statuses),
        "metrics": metrics,
        "thresholds": thresholds,
        "pending_cases": pending_cases,
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--backend")
    parser.add_argument("--run-id")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.prepare and args.results:
        raise SystemExit("Use only one of --prepare or --results")
    if args.prepare and (not args.backend or not args.run_id):
        raise SystemExit("--prepare requires --backend and --run-id")
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    database = workflow_paths(root)["database"]
    if not database.is_file():
        raise SystemExit("Catalog missing; run build_reference_index.py first")
    dataset_path = args.dataset.expanduser().resolve()
    dataset = load_dataset(dataset_path)
    if args.prepare:
        raise SystemExit(
            "This benchmark dataset uses retired identity-card inputs and cannot "
            "prepare new runs. Existing immutable runs may still be scored with "
            "--results. Build a new official-setting-sheet benchmark before further "
            "backend comparisons."
        )
    connection = open_database(database, read_only=True)
    try:
        cards, failures = validate_benchmark(dataset, root, connection)
        if args.prepare and not failures:
            run_dir = prepare_run(
                dataset,
                dataset_path,
                root,
                cards,
                connection,
                args.backend,
                args.run_id,
            )
            result = {
                "ok": True,
                "dataset": str(dataset_path),
                "case_count": len(dataset["cases"]),
                "run_dir": str(run_dir.resolve()),
                "failures": [],
            }
        elif args.results and not failures:
            result = score_run(
                dataset, args.results.expanduser().resolve(), dataset_path
            )
        else:
            result = {
                "ok": not failures,
                "dataset": str(dataset_path),
                "workflow_root": str(root),
                "case_count": len(dataset["cases"]),
                "identity_card_count": len(cards),
                "coverage": dataset.get("coverage_requirements", {}),
                "thresholds": dataset.get("thresholds", {}),
                "failures": failures,
            }
    finally:
        connection.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"generation_benchmark_cases={result.get('case_count', len(dataset['cases']))} "
            f"ok={str(result['ok']).lower()}"
        )
        if result.get("run_dir"):
            print(result["run_dir"])
        for failure in result.get("failures", []):
            print(f"FAIL: {failure}")
    return 2 if args.check and not result["ok"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
