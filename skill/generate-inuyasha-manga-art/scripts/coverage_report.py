#!/usr/bin/env python3
"""Report reference coverage by source, subject, form, and useful shot type."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from build_reference_index import freshness
from workflow_common import (
    CHARACTER_SUBJECTS,
    library_signature,
    load_config,
    open_database,
    workflow_paths,
    workflow_root,
)

DEFAULT_REQUIRED_SHOTS = ("close-up", "upper-body", "full-body", "action")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument(
        "--source",
        default="manga-curated",
        choices=("manga-curated", "tv-curated", "official", "selected-output"),
    )
    parser.add_argument("--subject", action="append", default=[])
    parser.add_argument("--required-shot", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = load_config()
    root = workflow_root(config, args.workflow_root)
    database = workflow_paths(root)["database"]
    if not database.is_file():
        raise SystemExit("Catalog missing; run build_reference_index.py first")
    fresh, reason = freshness(
        database,
        config,
        library_signature(config),
        workflow_paths(root)["annotations"],
    )
    if not fresh:
        raise SystemExit(f"Catalog is stale: {reason}; run build_reference_index.py")
    connection = open_database(database, read_only=True)
    rows = connection.execute(
        "SELECT item_id, subjects, forms, subject_forms, shot_types "
        "FROM items WHERE source_id = ? AND kind = 'image'",
        (args.source,),
    ).fetchall()
    connection.close()

    required = args.required_shot or list(DEFAULT_REQUIRED_SHOTS)
    subject_counts: dict[str, Counter[str]] = defaultdict(Counter)
    form_counts: dict[str, Counter[str]] = defaultdict(Counter)
    missing = Counter()
    for row in rows:
        subjects = json.loads(row["subjects"] or "[]")
        forms = json.loads(row["forms"] or "[]")
        subject_forms = json.loads(row["subject_forms"] or "{}")
        shots = json.loads(row["shot_types"] or "[]")
        if not subjects:
            missing["subject"] += 1
        if not forms:
            missing["form"] += 1
        if not shots:
            missing["shot"] += 1
        for subject in subjects:
            subject_counts[subject]["total"] += 1
            for shot in shots:
                subject_counts[subject][shot] += 1
            for form in subject_forms.get(subject, []):
                form_counts[subject][form] += 1

    selected_subjects = args.subject or sorted(
        set(subject_counts) & set(CHARACTER_SUBJECTS), key=str.casefold
    )
    coverage = []
    for subject in selected_subjects:
        counts = subject_counts[subject]
        coverage.append(
            {
                "subject": subject,
                "total": counts["total"],
                "forms": dict(form_counts[subject]),
                "shots": {shot: counts[shot] for shot in required},
                "missing_required_shots": [
                    shot for shot in required if not counts[shot]
                ],
            }
        )
    result = {
        "source": args.source,
        "unique_images": len(rows),
        "missing_metadata": dict(missing),
        "required_shots": required,
        "coverage": coverage,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"Source: {args.source}; unique images: {len(rows)}")
    print(
        "Missing metadata: "
        f"subject={missing['subject']} form={missing['form']} shot={missing['shot']}"
    )
    for row in coverage:
        shots = " ".join(f"{shot}={row['shots'][shot]}" for shot in required)
        gaps = ",".join(row["missing_required_shots"]) or "none"
        print(f"{row['subject']}: total={row['total']} {shots}; gaps={gaps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
