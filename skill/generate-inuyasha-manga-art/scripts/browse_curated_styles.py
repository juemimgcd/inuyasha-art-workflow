#!/usr/bin/env python3
"""Browse a curated screenshot or selected-output image source as a contact sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_reference_index import freshness
from image_sheet import build_contact_sheet
from task_workflow import feedback_rank, reference_performance
from workflow_common import (
    FORM_VALUES,
    REFERENCE_DOMAINS,
    SHOT_VALUES,
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

SOURCE_BY_MEDIUM = {"manga": "manga-curated", "tv": "tv-curated"}
SOURCE_CHOICES = ("manga-curated", "tv-curated", "selected-output")


def parse_preferred_subject_form(value: str) -> tuple[str, str]:
    subject, separator, form = value.partition("=")
    subject = subject.strip()
    form = form.strip()
    if not separator or not subject or form not in FORM_VALUES:
        raise argparse.ArgumentTypeError(
            "preferred subject form must look like CHARACTER=FORM"
        )
    return subject, form


def hard_facet_filters(
    *,
    reference_domain: str | None,
    role: str | None,
    preferred_subject_forms: list[tuple[str, str]],
    subjects: list[str],
    shots: list[str],
) -> tuple[tuple[str, list[str]], ...]:
    """Return facets that are safe to apply before relevance ranking.

    A requested shot remains a useful character-style scoring signal, but it
    must not eliminate an exact focal character-form before ranking.  Explicit
    identity/content queries without a preferred character-form retain the
    historical hard shot filter.
    """
    filters: list[tuple[str, list[str]]] = [("subjects", subjects)]
    rendering_style_search = role == "rendering" and reference_domain in {
        "character-style",
        "scene",
    }
    if not rendering_style_search:
        filters.append(("shot_types", shots))
    return tuple(filters)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument(
        "--reference-domain",
        choices=REFERENCE_DOMAINS,
        help="Hard authority-domain filter applied before ranking.",
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--medium", choices=("manga", "tv"))
    source_group.add_argument("--source", choices=SOURCE_CHOICES)
    parser.add_argument(
        "--query", default="", help="Optional filename, tag, or note terms."
    )
    parser.add_argument(
        "--intent-text",
        default="",
        help=(
            "Natural-language request used only to rank controlled trait matches; "
            "it never hard-filters candidates or changes evidence authority."
        ),
    )
    parser.add_argument(
        "--exact-term",
        action="append",
        default=[],
        help=(
            "Exact structured filename term, tag, or content label; repeat to "
            "require several terms. Prefer this for content evidence."
        ),
    )
    parser.add_argument(
        "--exclude-exact-term",
        action="append",
        default=[],
        help=(
            "Exclude an exact structured filename term, tag, or content label. "
            "Used when a canonical scene hit cannot also cover scene rendering."
        ),
    )
    parser.add_argument("--match", choices=("all", "any"), default="all")
    parser.add_argument(
        "--folder",
        action="append",
        default=[],
        help="Exact inherited folder-name tag; repeat to require several folders.",
    )
    parser.add_argument(
        "--content",
        action="append",
        default=[],
        help="Exact leaf content-folder name; repeat to include alternatives.",
    )
    parser.add_argument("--subject", action="append", default=[])
    parser.add_argument("--form", action="append", default=[], choices=FORM_VALUES)
    parser.add_argument(
        "--prefer-subject-form",
        action="append",
        type=parse_preferred_subject_form,
        default=[],
        help=(
            "Small boost for a rendering candidate that depicts a focal "
            "character-form; never hard-filters or grants identity authority."
        ),
    )
    parser.add_argument("--shot", action="append", default=[], choices=SHOT_VALUES)
    parser.add_argument(
        "--view-angle",
        choices=VIEW_ANGLE_VALUES,
        help=(
            "Preferred character-view applicability. This is a strong ranking "
            "signal for character-style evidence, never pose authority."
        ),
    )
    parser.add_argument(
        "--role",
        choices=("rendering", "composition", "content", "continuity"),
        help="Require item-level eligibility for this evidence role.",
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.offset < 0:
        raise SystemExit("--offset must be zero or greater")
    if args.limit < 1 or args.limit > 30:
        raise SystemExit("--limit must be between 1 and 30")
    if args.columns < 1 or args.columns > 6:
        raise SystemExit("--columns must be between 1 and 6")

    config = load_config()
    root = workflow_root(config, args.workflow_root)
    paths = workflow_paths(root)
    database = paths["database"]
    if not database.is_file():
        raise SystemExit("Catalog missing; run build_reference_index.py first")
    fresh, reason = freshness(
        database, config, library_signature(config), paths["annotations"]
    )
    if not fresh:
        raise SystemExit(f"Catalog is stale: {reason}; run build_reference_index.py")

    source_id = args.source or SOURCE_BY_MEDIUM[args.medium or "manga"]
    clauses = ["source_id = ?", "kind = 'image'"]
    parameters: list[object] = [source_id]
    if args.reference_domain:
        clauses.append("reference_domain = ?")
        parameters.append(args.reference_domain)
    if args.role:
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(eligible_roles) AS eligible_role "
            "WHERE eligible_role.value = ? COLLATE NOCASE)"
        )
        parameters.append(args.role)
    terms = [term.casefold() for term in args.query.split() if term.strip()]
    inferred_traits = retrieval_traits_for(
        args.intent_text,
        args.shot[0] if args.role == "rendering" and len(args.shot) == 1 else None,
        medium=(
            "manga"
            if source_id == "manga-curated"
            else "tv"
            if source_id == "tv-curated"
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
    excluded_scoring_terms = {term.casefold() for term in args.exclude_exact_term}
    scoring_terms = [
        term
        for term in dict.fromkeys([*terms, *intent_traits])
        if term.casefold() not in excluded_scoring_terms
        and not (
            args.view_angle
            and term.casefold() == f"view-angle:{args.view_angle}".casefold()
        )
    ]
    if terms:
        joiner = " AND " if args.match == "all" else " OR "
        clauses.append("(" + joiner.join("search_text LIKE ?" for _ in terms) + ")")
        parameters.extend(f"%{term}%" for term in terms)
    for term in args.exact_term:
        clauses.append(
            "(EXISTS (SELECT 1 FROM json_each(filename_terms) AS filename_term "
            "WHERE filename_term.value = ? COLLATE NOCASE) OR "
            "EXISTS (SELECT 1 FROM json_each(tags) AS exact_tag "
            "WHERE exact_tag.value = ? COLLATE NOCASE) OR "
            "EXISTS (SELECT 1 FROM item_locations AS exact_location "
            "WHERE exact_location.item_id = items.item_id "
            "AND exact_location.content_label = ? COLLATE NOCASE))"
        )
        parameters.extend((term, term, term))
    for term in args.exclude_exact_term:
        clauses.append(
            "NOT (EXISTS (SELECT 1 FROM json_each(filename_terms) AS filename_term "
            "WHERE filename_term.value = ? COLLATE NOCASE) OR "
            "EXISTS (SELECT 1 FROM json_each(tags) AS exact_tag "
            "WHERE exact_tag.value = ? COLLATE NOCASE) OR "
            "EXISTS (SELECT 1 FROM item_locations AS exact_location "
            "WHERE exact_location.item_id = items.item_id "
            "AND exact_location.content_label = ? COLLATE NOCASE))"
        )
        parameters.extend((term, term, term))
    for folder in args.folder:
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(folder_tags) AS folder_tag "
            "WHERE folder_tag.value = ? COLLATE NOCASE)"
        )
        parameters.append(folder)
    if args.content:
        content_clauses = [
            "EXISTS (SELECT 1 FROM item_locations AS location "
            "WHERE location.item_id = items.item_id "
            "AND location.content_label = ? COLLATE NOCASE)"
            for _ in args.content
        ]
        clauses.append(f"({' OR '.join(content_clauses)})")
        parameters.extend(args.content)
    for column, values in hard_facet_filters(
        reference_domain=args.reference_domain,
        role=args.role,
        preferred_subject_forms=args.prefer_subject_form,
        subjects=args.subject,
        shots=args.shot,
    ):
        if values:
            clauses.append(
                "("
                + " OR ".join(
                    f"EXISTS (SELECT 1 FROM json_each({column}) AS facet "
                    "WHERE facet.value = ? COLLATE NOCASE)"
                    for _ in values
                )
                + ")"
            )
            parameters.extend(values)
    pairs: list[tuple[str, str]] = []
    if args.subject and args.form:
        if len(args.subject) > 1 and len(args.form) > 1 and len(args.subject) != len(args.form):
            raise SystemExit(
                "Multiple --subject and --form values must be one shared form or equal-length pairs"
            )
        if len(args.form) == 1:
            pairs = [(subject, args.form[0]) for subject in args.subject]
        elif len(args.subject) == 1:
            pairs = [(args.subject[0], form) for form in args.form]
        else:
            pairs = list(zip(args.subject, args.form))
        pair_clauses = []
        for subject, form in pairs:
            pair_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(subject_forms) AS subject_form "
                "JOIN json_each(subject_form.value) AS compatible_form "
                "WHERE subject_form.key = ? COLLATE NOCASE "
                "AND compatible_form.value = ? COLLATE NOCASE)"
            )
            parameters.extend((subject, form))
        joiner = " OR " if len(args.subject) == 1 else " AND "
        clauses.append(f"({joiner.join(pair_clauses)})")
    elif args.form:
        clauses.append(
            "(" + " OR ".join(
                "EXISTS (SELECT 1 FROM json_each(forms) AS facet "
                "WHERE facet.value = ? COLLATE NOCASE)"
                for _ in args.form
            ) + ")"
        )
        parameters.extend(args.form)

    connection = open_database(database, read_only=True)
    rows = connection.execute(
        f"""
        SELECT item_id, path, relative_path, width, height, tags, note,
               folder_path, content_label, folder_tags, subjects, forms,
               subject_forms, shot_types, filename_terms, duplicate_count,
               eligible_roles
               , reference_domain
        FROM items
        WHERE {" AND ".join(clauses)}
        ORDER BY relative_path COLLATE NOCASE
        """,
        parameters,
    ).fetchall()
    total = connection.execute(
        f"SELECT COUNT(*) FROM items WHERE {' AND '.join(clauses)}", parameters
    ).fetchone()[0]
    connection.close()
    if not rows:
        raise SystemExit(f"No images from {source_id} matched this page or query")

    performance = reference_performance(paths["tasks"])
    candidates = []
    for row in rows:
        candidate = dict(row)
        candidate["tags"] = json.loads(candidate["tags"])
        candidate["folder_tags"] = json.loads(candidate["folder_tags"])
        for field in (
            "subjects",
            "forms",
            "subject_forms",
            "shot_types",
            "filename_terms",
            "eligible_roles",
        ):
            candidate[field] = json.loads(candidate[field])
        candidate["score"], candidate["match_reasons"] = retrieval_relevance(
            candidate,
            query_terms=scoring_terms,
            exact_terms=args.exact_term,
            subjects=args.subject,
            subject_forms=pairs,
            preferred_subject_forms=args.prefer_subject_form,
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
        if args.reference_domain == "scene" and any(
            term.startswith("scene-id:") for term in args.exact_term
        ):
            structure_boosts = {
                "scene-structure:overall": 4,
                "scene-structure:detail": 2,
                "scene-structure:spatial-relation": 1,
            }
            for tag, boost in structure_boosts.items():
                if tag in candidate["tags"]:
                    candidate["score"] += boost
                    candidate["match_reasons"].append(
                        f"canonical scene structure: {tag.rsplit(':', 1)[-1]}"
                    )
        candidate["feedback"] = performance.get(
            row["item_id"],
            {
                "accepted": 0,
                "rejected": 0,
                "total": 0,
                "smoothed_acceptance": 0.5,
            },
        )
        candidate["feedback_rank"] = round(feedback_rank(candidate["feedback"]), 4)
        candidate["certified_style_anchor"] = bool(
            certified_style_anchor_rank(
                candidate,
                role=args.role,
                reference_domain=args.reference_domain,
            )
        )
        if candidate["certified_style_anchor"]:
            candidate["match_reasons"].append(
                "certified style anchor (same-score tie-breaker)"
            )
        candidate["inferred_traits"] = inferred_traits
        candidate["scoring_traits"] = [
            trait
            for trait in intent_traits
            if trait.casefold() not in excluded_scoring_terms
        ]
        candidate["style_conflict_subjects"] = sorted(
            rendering_conflicts, key=str.casefold
        )
        candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            -int(candidate["certified_style_anchor"]),
            -candidate["feedback_rank"],
            candidate["relative_path"].casefold(),
        )
    )
    candidates = candidates[args.offset : args.offset + args.limit]
    if not candidates:
        raise SystemExit(f"No images from {source_id} matched this page or query")

    entries = []
    for index, candidate in enumerate(candidates, args.offset + 1):
        candidate["position"] = index
        content = candidate["content_label"] or Path(candidate["relative_path"]).stem
        entries.append(
            (
                Path(candidate["path"]),
                f"{index}. {content} | {Path(candidate['relative_path']).stem}",
            )
        )

    last = args.offset + len(candidates)
    filter_signature = json.dumps(
        {
            "source": source_id,
            "reference_domain": args.reference_domain,
            "query": args.query,
            "intent_text": args.intent_text,
            "inferred_traits": intent_traits,
            "exact_terms": args.exact_term,
            "excluded_exact_terms": args.exclude_exact_term,
            "folders": args.folder,
            "content": args.content,
            "subjects": args.subject,
            "forms": args.form,
            "preferred_subject_forms": args.prefer_subject_form,
            "shots": args.shot,
            "view_angle": args.view_angle,
            "role": args.role,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    has_filters = bool(
        args.query
        or args.intent_text
        or args.exact_term
        or args.exclude_exact_term
        or args.folder
        or args.content
        or args.subject
        or args.form
        or args.shot
        or args.view_angle
        or args.role
        or args.reference_domain
    )
    query_suffix = (
        f"-q{hashlib.sha1(filter_signature.encode('utf-8')).hexdigest()[:8]}"
        if has_filters
        else ""
    )
    output = args.output or (
        paths["contact_sheets"]
        / source_id
        / f"items-{args.offset + 1:04d}-{last:04d}{query_suffix}.jpg"
    )
    output = output.expanduser().resolve()
    build_contact_sheet(entries, output, columns=args.columns)

    result = {
        "source_id": source_id,
        "reference_domain": args.reference_domain,
        "medium": args.medium,
        "query": args.query,
        "intent_text": args.intent_text,
        "inferred_traits": intent_traits,
        "style_conflict_subjects": sorted(rendering_conflicts, key=str.casefold),
        "exact_terms": args.exact_term,
        "excluded_exact_terms": args.exclude_exact_term,
        "folders": args.folder,
        "content": args.content,
        "subjects": args.subject,
        "forms": args.form,
        "preferred_subject_forms": args.prefer_subject_form,
        "shots": args.shot,
        "view_angle": args.view_angle,
        "role": args.role,
        "offset": args.offset,
        "returned": len(candidates),
        "total_matches": total,
        "contact_sheet": str(output),
        "candidates": candidates,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if intent_traits:
            print(f"Scoring traits: {' '.join(intent_traits)}")
        for row in candidates:
            print(f"[{row['position']}] {row['item_id']}")
            print(f"  {row['path']}")
            print(f"  domain: {row['reference_domain']}")
            if row["folder_tags"]:
                print(
                    f"  folders: {' / '.join(row['folder_tags'])}; "
                    f"content: {row['content_label']}"
                )
            if row["match_reasons"]:
                print(f"  matched: {'; '.join(row['match_reasons'])}")
        print(f"Contact sheet: {output}")
        print(f"Showing {args.offset + 1}-{last} of {total} matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
