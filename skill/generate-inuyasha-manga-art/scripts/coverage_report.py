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
    FORM_VALUES,
    KNOWN_SUBJECTS,
    OFFICIAL_IDENTITY_FACETS,
    library_signature,
    load_config,
    open_database,
    official_facet_coverage,
    workflow_paths,
    workflow_root,
)

DEFAULT_REQUIRED_SHOTS = ("close-up", "upper-body", "full-body", "action")


def parse_subject_form(value: str) -> tuple[str, str]:
    subject, separator, form = value.partition("=")
    if not separator or subject not in KNOWN_SUBJECTS or form not in FORM_VALUES:
        raise argparse.ArgumentTypeError(
            "subject-form must look like SUBJECT=FORM with known values"
        )
    return subject, form


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument(
        "--source",
        default="manga-curated",
        choices=("manga-curated", "tv-curated", "official", "selected-output"),
    )
    parser.add_argument("--subject", action="append", default=[])
    parser.add_argument(
        "--subject-form", type=parse_subject_form, action="append", default=[]
    )
    parser.add_argument("--required-shot", action="append", default=[])
    parser.add_argument(
        "--required-facet",
        action="append",
        default=[],
        choices=OFFICIAL_IDENTITY_FACETS,
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if bool(args.subject_form) != bool(args.required_facet):
        raise SystemExit(
            "--subject-form and --required-facet must be used together"
        )
    if args.required_facet and args.source != "official":
        raise SystemExit("official facet coverage requires --source official")

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
        "SELECT item_id, relative_path, subjects, forms, subject_forms, shot_types, tags, eligible_roles "
        "FROM items WHERE source_id = ? AND kind = 'image'",
        (args.source,),
    ).fetchall()
    connection.close()

    facet_coverage = [
        official_facet_coverage(rows, subject, form, args.required_facet)
        for subject, form in args.subject_form
    ]

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

    selected_subjects = args.subject or (
        []
        if args.subject_form
        else sorted(set(subject_counts) & set(CHARACTER_SUBJECTS), key=str.casefold)
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
        "facet_coverage": facet_coverage,
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
    for row in facet_coverage:
        print(
            f"{row['subject']}={row['form']}: {row['status']}; "
            f"missing={','.join(row['missing_facets']) or 'none'}"
        )
        for facet, providers in row["providers"].items():
            print(f"  {facet}: {','.join(providers) or 'INSUFFICIENT'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
