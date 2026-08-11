#!/usr/bin/env python3
"""Append a durable manual annotation for one indexed reference item."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_common import (
    load_config,
    now_iso,
    open_database,
    workflow_paths,
    workflow_root,
)

VISUAL_TRAIT_VALUES = {
    "scene-energy": {"quiet", "dialogue", "action", "impact"},
    "face-clarity": {"low", "medium", "high"},
    "line-weight": {"soft-variable", "firm-variable", "heavy-action"},
    "tone-density": {"light", "balanced", "dense"},
    "black-mass": {
        "hair-dominant",
        "effect-dominant",
        "background-dominant",
        "balanced",
    },
    "background": {"minimal", "nature", "architecture", "night", "interior"},
    "effect-type": {"none", "wind", "rain", "mist", "speed-lines", "impact", "aura"},
    "suitable-for": {
        "close-up",
        "two-shot",
        "full-body",
        "back-view",
        "quiet-scene",
        "combat",
        "establishing",
        "weapon-mount",
        "garment-overlap",
        "footwear",
        "ground-contact",
    },
    "view-angle": {
        "front",
        "three-quarter-front",
        "profile",
        "three-quarter-back",
        "back",
        "high-angle",
        "low-angle",
        "multi-view",
    },
    "depth-layout": {"same-plane", "foreground-midground", "foreground-background", "layered"},
    "occlusion": {"clear", "partial", "heavy", "body-body", "garment-body", "garment-prop"},
    "contact-type": {"none", "ground", "body", "prop", "clothing"},
    "prop-attachment": {"none", "waist", "back", "hand", "shoulder", "clothing"},
    "perspective-risk": {"low", "medium", "high"},
}


def parse_trait(value: str) -> str:
    key, separator, trait_value = value.partition("=")
    if not separator or key not in VISUAL_TRAIT_VALUES or not trait_value.strip():
        allowed = ", ".join(sorted(VISUAL_TRAIT_VALUES))
        raise argparse.ArgumentTypeError(
            f"trait must look like KEY=VALUE; allowed keys: {allowed}"
        )
    normalized = trait_value.strip().lower().replace(" ", "-")
    if normalized not in VISUAL_TRAIT_VALUES[key]:
        allowed_values = ", ".join(sorted(VISUAL_TRAIT_VALUES[key]))
        raise argparse.ArgumentTypeError(
            f"unsupported value for {key}: {normalized}; allowed: {allowed_values}"
        )
    return f"{key}:{normalized}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--tags", nargs="+", default=[])
    parser.add_argument("--trait", type=parse_trait, action="append", default=[])
    parser.add_argument("--note", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.tags and not args.trait and not args.note:
        raise SystemExit("Provide --tags, --trait, --note, or a combination")
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    paths = workflow_paths(root)
    if not paths["database"].is_file():
        raise SystemExit("Catalog missing; run build_reference_index.py first")
    connection = open_database(paths["database"], read_only=True)
    resolved = connection.execute(
        """
        SELECT item_id FROM items WHERE item_id = ?
        UNION ALL
        SELECT item_id FROM item_aliases WHERE alias_id = ?
        LIMIT 1
        """,
        (args.item_id, args.item_id),
    ).fetchone()
    connection.close()
    if resolved is None:
        raise SystemExit(f"Unknown catalog item: {args.item_id}")
    canonical_item_id = resolved["item_id"]
    annotations = paths["annotations"]
    annotations.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "item_id": canonical_item_id,
        "tags": sorted(set(args.tags) | set(args.trait)),
        "note": args.note,
        "annotated_at": now_iso(),
    }
    with annotations.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Annotated {canonical_item_id}")
    print("Refresh with build_reference_index.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
