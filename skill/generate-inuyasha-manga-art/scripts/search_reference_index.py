#!/usr/bin/env python3
"""Search the local Inuyasha reference catalog without crossing evidence layers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from build_reference_index import freshness
from task_workflow import feedback_rank, reference_performance
from workflow_common import (
    FORM_VALUES,
    KNOWN_SUBJECTS,
    SHOT_VALUES,
    library_signature,
    load_config,
    open_database,
    workflow_paths,
    workflow_root,
)


def parse_subject_form(value: str) -> tuple[str, str]:
    subject, separator, form = value.partition("=")
    if not separator or subject not in KNOWN_SUBJECTS or form not in FORM_VALUES:
        raise argparse.ArgumentTypeError(
            "subject-form must look like CHARACTER=FORM with known values"
        )
    return subject, form


def parse_page_range(value: str) -> tuple[int, int]:
    try:
        start_text, end_text = value.split("-", 1)
        start, end = int(start_text), int(end_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("page range must look like START-END") from exc
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("page range must be positive and ordered")
    return start, end


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument(
        "--source", help="One source id, such as official or manga-curated."
    )
    parser.add_argument(
        "--medium", choices=("identity", "manga", "tv", "user-original")
    )
    parser.add_argument(
        "--role",
        choices=(
            "identity",
            "rendering",
            "composition",
            "content",
            "continuity",
            "target",
            "palette",
        ),
        help="Filter sources that are authoritative for this evidence role.",
    )
    parser.add_argument("--kind", choices=("image", "pdf", "pdf_page"))
    parser.add_argument(
        "--query", default="", help="Whitespace-separated terms; all match by default."
    )
    parser.add_argument("--match", choices=("all", "any"), default="all")
    parser.add_argument(
        "--folder",
        action="append",
        default=[],
        help="Exact folder-name tag; repeat to combine inherited directory labels.",
    )
    parser.add_argument("--folder-match", choices=("all", "any"), default="all")
    parser.add_argument(
        "--content",
        action="append",
        default=[],
        help="Exact leaf folder name describing screenshot content; repeat for alternatives.",
    )
    parser.add_argument(
        "--subject",
        action="append",
        default=[],
        help="Exact indexed subject, such as 犬夜叉; repeat as needed.",
    )
    parser.add_argument("--subject-match", choices=("all", "any"), default="all")
    parser.add_argument(
        "--subject-form",
        type=parse_subject_form,
        action="append",
        default=[],
        metavar="CHARACTER=FORM",
        help="Match a character and form as one pair; repeat for multi-character art.",
    )
    parser.add_argument(
        "--form",
        action="append",
        default=[],
        choices=FORM_VALUES,
        help="Exact compatible character form; repeat to accept alternatives.",
    )
    parser.add_argument(
        "--exclude-form",
        action="append",
        default=[],
        choices=FORM_VALUES,
        help="Reject references tagged with this character form.",
    )
    parser.add_argument(
        "--shot",
        action="append",
        default=[],
        choices=SHOT_VALUES,
        help="Exact indexed shot type; repeat to accept alternatives.",
    )
    parser.add_argument("--volume", type=int)
    parser.add_argument("--page", type=int)
    parser.add_argument("--page-range", type=parse_page_range)
    parser.add_argument("--curated-only", action="store_true")
    parser.add_argument("--include-unannotated-pages", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def source_ids_for_role(connection: Any, role: str) -> list[str]:
    rows = connection.execute(
        "SELECT source_id, evidence_roles FROM sources"
    ).fetchall()
    return [
        row["source_id"] for row in rows if role in json.loads(row["evidence_roles"])
    ]


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.limit > 200:
        raise SystemExit("--limit must be between 1 and 200")
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    database = workflow_paths(root)["database"]
    if not database.is_file():
        raise SystemExit(f"Catalog missing: {database}; run build_reference_index.py")
    fresh, reason = freshness(
        database,
        config,
        library_signature(config),
        workflow_paths(root)["annotations"],
    )
    if not fresh:
        raise SystemExit(f"Catalog is stale: {reason}; run build_reference_index.py")
    if args.subject_form and (args.subject or args.form):
        raise SystemExit("Use --subject-form or --subject/--form, not both")
    connection = open_database(database, read_only=True)

    clauses: list[str] = []
    parameters: list[Any] = []
    if args.source:
        clauses.append("items.source_id = ?")
        parameters.append(args.source)
    if args.medium:
        clauses.append("sources.medium = ?")
        parameters.append(args.medium)
    if args.role:
        allowed = source_ids_for_role(connection, args.role)
        if not allowed:
            print("No sources support that evidence role.")
            return 1
        clauses.append(f"items.source_id IN ({', '.join('?' for _ in allowed)})")
        parameters.extend(allowed)
    if args.kind:
        clauses.append("items.kind = ?")
        parameters.append(args.kind)
    if args.volume is not None:
        clauses.append("items.volume = ?")
        parameters.append(args.volume)
    if args.page is not None:
        clauses.append("items.pdf_page = ?")
        parameters.append(args.page)
    if args.page_range:
        clauses.append("items.pdf_page BETWEEN ? AND ?")
        parameters.extend(args.page_range)
    if args.curated_only:
        clauses.append("items.curated = 1")

    if args.folder:
        folder_clauses = [
            "EXISTS (SELECT 1 FROM json_each(items.folder_tags) AS folder_tag "
            "WHERE folder_tag.value = ? COLLATE NOCASE)"
            for _ in args.folder
        ]
        joiner = " AND " if args.folder_match == "all" else " OR "
        clauses.append(f"({joiner.join(folder_clauses)})")
        parameters.extend(args.folder)
    if args.content:
        content_clauses = [
            "EXISTS (SELECT 1 FROM item_locations AS location "
            "WHERE location.item_id = items.item_id "
            "AND location.content_label = ? COLLATE NOCASE)"
            for _ in args.content
        ]
        clauses.append(f"({' OR '.join(content_clauses)})")
        parameters.extend(args.content)

    def add_json_facet(
        column: str, values: list[str], match: str = "any", negate: bool = False
    ) -> None:
        if not values:
            return
        comparisons = [
            f"{'NOT ' if negate else ''}EXISTS "
            f"(SELECT 1 FROM json_each(items.{column}) AS facet "
            "WHERE facet.value = ? COLLATE NOCASE)"
            for _ in values
        ]
        joiner = " AND " if match == "all" or negate else " OR "
        clauses.append(f"({joiner.join(comparisons)})")
        parameters.extend(values)

    add_json_facet("subjects", args.subject, args.subject_match)

    def add_subject_form_groups(
        groups: dict[str, list[str]], *, negate: bool = False
    ) -> None:
        if not groups:
            return
        comparisons = []
        for subject, forms in groups.items():
            placeholders = ", ".join("?" for _ in forms)
            exists = (
                "EXISTS (SELECT 1 FROM json_each(items.subject_forms) AS subject_form "
                "JOIN json_each(subject_form.value) AS compatible_form "
                "WHERE subject_form.key = ? COLLATE NOCASE "
                f"AND compatible_form.value IN ({placeholders}))"
            )
            comparisons.append(f"NOT {exists}" if negate else exists)
            parameters.append(subject)
            parameters.extend(forms)
        joiner = " AND " if args.subject_match == "all" or negate else " OR "
        clauses.append(f"({joiner.join(comparisons)})")

    paired_forms: dict[str, list[str]] = {}
    if args.subject_form:
        for subject, form in args.subject_form:
            paired_forms.setdefault(subject, []).append(form)
    elif args.subject and args.form:
        if len(args.subject) > 1 and len(args.form) > 1 and len(args.subject) != len(args.form):
            raise SystemExit(
                "Multiple --subject and --form values must be one shared form or equal-length pairs"
            )
        if len(args.form) == 1:
            paired_forms = {subject: list(args.form) for subject in args.subject}
        elif len(args.subject) == 1:
            paired_forms = {args.subject[0]: list(args.form)}
        else:
            for subject, form in zip(args.subject, args.form):
                paired_forms.setdefault(subject, []).append(form)
    add_subject_form_groups(paired_forms)
    if args.form and not args.subject:
        add_json_facet("forms", args.form, "any")
    if args.exclude_form and args.subject:
        add_subject_form_groups(
            {subject: list(args.exclude_form) for subject in args.subject}, negate=True
        )
    else:
        add_json_facet("forms", args.exclude_form, "all", negate=True)
    add_json_facet("shot_types", args.shot, "any")

    terms = [term.casefold() for term in args.query.split() if term.strip()]
    if terms:
        term_clauses = ["items.search_text LIKE ?" for _ in terms]
        joiner = " AND " if args.match == "all" else " OR "
        clauses.append(f"({joiner.join(term_clauses)})")
        parameters.extend(f"%{term}%" for term in terms)

    if (
        not args.include_unannotated_pages
        and args.kind != "pdf_page"
        and args.volume is None
        and args.page is None
        and args.page_range is None
    ):
        clauses.append("NOT (items.kind = 'pdf_page' AND items.curated = 0)")

    score_sql = "0"
    if terms:
        score_sql = " + ".join(
            "CASE WHEN items.search_text LIKE ? THEN 1 ELSE 0 END" for _ in terms
        )
        score_parameters = [f"%{term}%" for term in terms]
    else:
        score_parameters = []

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT items.*, sources.label AS source_label, sources.medium,
               sources.authority, ({score_sql}) AS score
        FROM items
        JOIN sources ON sources.source_id = items.source_id
        {where}
        ORDER BY score DESC, items.curated DESC, items.source_id,
                 COALESCE(items.volume, 0), COALESCE(items.pdf_page, 0), items.relative_path
    """
    rows = connection.execute(query, [*score_parameters, *parameters]).fetchall()
    connection.close()

    performance = reference_performance(workflow_paths(root)["tasks"])
    output = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags"])
        item["folder_tags"] = json.loads(item["folder_tags"])
        for field in (
            "subjects",
            "forms",
            "subject_forms",
            "shot_types",
            "filename_terms",
        ):
            item[field] = json.loads(item[field])
        item.pop("search_text", None)
        item["feedback"] = performance.get(
            item["item_id"],
            {
                "accepted": 0,
                "rejected": 0,
                "total": 0,
                "smoothed_acceptance": 0.5,
            },
        )
        item["feedback_rank"] = round(feedback_rank(item["feedback"]), 4)
        output.append(item)
    output.sort(
        key=lambda item: (
            -item["score"],
            -item["feedback_rank"],
            item["relative_path"].casefold(),
        )
    )
    output = output[: args.limit]

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output else 1

    if not output:
        print("No matching references.")
        return 1
    for item in output:
        locator = item["path"]
        if item["kind"] == "pdf_page":
            locator += f"#page={item['pdf_page']}"
        dimensions = ""
        if item.get("width") and item.get("height"):
            dimensions = f" {item['width']}x{item['height']}"
        curated = " curated" if item["curated"] else ""
        print(
            f"{item['item_id']} [{item['source_id']}/{item['kind']}{curated}]{dimensions}"
        )
        print(f"  {locator}")
        if item["note"]:
            print(f"  note: {item['note']}")
        if item["folder_tags"]:
            print(
                f"  folders: {' / '.join(item['folder_tags'])}; "
                f"content: {item['content_label']}"
            )
        if item["duplicate_count"] > 1:
            print(f"  duplicate locations: {item['duplicate_count']}")
        print(
            "  facets: "
            f"subjects={','.join(item['subjects']) or '-'}; "
            f"forms={','.join(item['forms']) or '-'}; "
            f"shots={','.join(item['shot_types']) or '-'}"
        )
        print(f"  subject forms: {json.dumps(item['subject_forms'], ensure_ascii=False)}")
        print(f"  tags: {' '.join(item['tags'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
