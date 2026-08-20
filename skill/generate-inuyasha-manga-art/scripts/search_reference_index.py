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
    REFERENCE_DOMAINS,
    SHOT_VALUES,
    VIEW_ANGLE_SHOT_MAP,
    VIEW_ANGLE_VALUES,
    certified_style_anchor_rank,
    library_signature,
    load_config,
    open_database,
    retrieval_relevance,
    retrieval_traits_for,
    retrieval_traits_for_domain,
    style_conflict_subjects,
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
        "--reference-domain",
        choices=REFERENCE_DOMAINS,
        help="Hard authority-domain filter applied before relevance scoring.",
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
    parser.add_argument(
        "--intent-text",
        default="",
        help=(
            "Natural-language request used only to boost controlled trait matches; "
            "it never hard-filters candidates or changes evidence authority."
        ),
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
    parser.add_argument(
        "--view-angle",
        choices=VIEW_ANGLE_VALUES,
        help=(
            "Require an exact controlled view-angle tag or its documented shot "
            "facet equivalent. Use a shotless/viewless fallback only to prepare "
            "a focused crop, never to claim view coverage."
        ),
    )
    parser.add_argument("--volume", type=int)
    parser.add_argument("--page", type=int)
    parser.add_argument("--page-range", type=parse_page_range)
    parser.add_argument("--curated-only", action="store_true")
    parser.add_argument("--include-unannotated-pages", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


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
    if args.reference_domain:
        clauses.append("items.reference_domain = ?")
        parameters.append(args.reference_domain)
    if args.medium:
        clauses.append("sources.medium = ?")
        parameters.append(args.medium)
    if args.role:
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(items.eligible_roles) AS eligible_role "
            "WHERE eligible_role.value = ? COLLATE NOCASE)"
        )
        parameters.append(args.role)
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
        if (
            len(args.subject) > 1
            and len(args.form) > 1
            and len(args.subject) != len(args.form)
        ):
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
    if args.view_angle:
        view_conditions = [
            (
                "EXISTS (SELECT 1 FROM json_each(items.tags) AS view_tag "
                "WHERE view_tag.value = ? COLLATE NOCASE)"
            )
        ]
        parameters.append(f"view-angle:{args.view_angle}")
        shot_alias = VIEW_ANGLE_SHOT_MAP.get(args.view_angle)
        if shot_alias:
            view_conditions.append(
                "EXISTS (SELECT 1 FROM json_each(items.shot_types) AS view_shot "
                "WHERE view_shot.value = ? COLLATE NOCASE)"
            )
            parameters.append(shot_alias)
        clauses.append(f"({' OR '.join(view_conditions)})")

    terms = [term.casefold() for term in args.query.split() if term.strip()]
    inferred_traits = retrieval_traits_for(
        args.intent_text,
        args.shot[0] if args.role == "rendering" and len(args.shot) == 1 else None,
        medium=(
            "manga"
            if args.source == "manga-curated" or args.medium == "manga"
            else "tv"
            if args.source == "tv-curated" or args.medium == "tv"
            else None
        ),
    )
    intent_traits = retrieval_traits_for_domain(
        inferred_traits, args.reference_domain
    )
    rendering_conflicts = (
        style_conflict_subjects(args.intent_text)
        if args.role == "rendering" and args.reference_domain != "scene"
        else set()
    )
    scoring_terms = list(dict.fromkeys([*terms, *intent_traits]))
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

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT items.*, sources.label AS source_label, sources.medium
        FROM items
        JOIN sources ON sources.source_id = items.source_id
        {where}
        ORDER BY items.curated DESC, items.source_id,
                 COALESCE(items.volume, 0), COALESCE(items.pdf_page, 0), items.relative_path
    """
    rows = connection.execute(query, parameters).fetchall()
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
            "eligible_roles",
        ):
            item[field] = json.loads(item[field])
        item.pop("search_text", None)
        item["score"], item["match_reasons"] = retrieval_relevance(
            item,
            query_terms=scoring_terms,
            subjects=args.subject,
            subject_forms=[
                (subject, form)
                for subject, forms in paired_forms.items()
                for form in forms
            ],
            shots=args.shot,
            view_angles=[args.view_angle] if args.view_angle else [],
            folders=args.folder,
            contents=args.content,
            penalized_subjects=rendering_conflicts,
            role=args.role,
            shot_weight=(
                1
                if args.reference_domain == "scene" and args.role == "rendering"
                else 4
            ),
        )
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
        item["certified_style_anchor"] = bool(
            certified_style_anchor_rank(
                item,
                role=args.role,
                reference_domain=args.reference_domain,
            )
        )
        if item["certified_style_anchor"]:
            item["match_reasons"].append(
                "certified style anchor (same-score tie-breaker)"
            )
        item["inferred_traits"] = inferred_traits
        item["scoring_traits"] = intent_traits
        item["style_conflict_subjects"] = sorted(
            rendering_conflicts, key=str.casefold
        )
        output.append(item)
    output.sort(
        key=lambda item: (
            -item["score"],
            -int(item["certified_style_anchor"]),
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
    if intent_traits:
        print(f"Scoring traits: {' '.join(intent_traits)}")
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
        print(f"  domain: {item['reference_domain']}")
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
        print(
            f"  subject forms: {json.dumps(item['subject_forms'], ensure_ascii=False)}"
        )
        if item["match_reasons"]:
            print(f"  matched: {'; '.join(item['match_reasons'])}")
        print(f"  tags: {' '.join(item['tags'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
