#!/usr/bin/env python3
"""Append a durable manual annotation for one indexed reference item."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_common import (
    FORM_VALUES,
    OFFICIAL_IDENTITY_FACETS,
    identity_facet_tag,
    load_config,
    now_iso,
    open_database,
    workflow_paths,
    workflow_root,
)

VISUAL_TRAIT_VALUES = {
    "style-anchor": {"certified"},
    "scene-class": {"canonical", "generic"},
    "scene-id": {"bone-eaters-well", "goshinboku"},
    "scene-family": {"architecture", "nature", "settlement", "interior", "canonical-landmark"},
    "scene-structure": {"overall", "detail", "spatial-relation"},
    "action": {
        "embrace",
        "embrace-from-behind",
        "look-down",
        "reach",
        "hold",
        "cut",
        "turn-head",
        "look-up",
        "sleeve-hidden-hands",
        "face-off",
        "draw-weapon",
        "swing-weapon",
        "jump",
        "run",
        "sit",
        "kneel",
        "carry",
        "crouch",
        "pass-ball",
        "catch-ball",
        "kick-ball",
        "comb-hair",
        "touch-ears",
        "adjust-clothing",
        "activate-wind-tunnel",
        "sheath-weapon",
        "ride",
        "fly",
        "transform",
        "conjure",
        "fall",
    },
    "interaction": {
        "mother-child",
        "romantic",
        "face-to-face",
        "body-contact",
        "hand-prop",
        "hand-clothing",
        "shoulder-rest",
        "shared-gaze",
        "confrontation",
        "caregiving",
        "teaching",
        "ear-touch",
        "rider-mount",
        "scale-reference",
    },
    "expression": {
        "alert-sad",
        "shy",
        "surprised",
        "gentle",
        "restrained",
        "angry",
        "determined",
        "crying",
        "neutral",
    },
    "content-object": {
        "knife",
        "daikon",
        "grave",
        "tessaiga",
        "tenseiga",
        "ball",
        "shopping-bag",
        "bow",
        "well",
        "tree",
        "comb",
        "mirror",
        "hair-ribbon",
        "robe-sleeve",
        "shrine",
        "beads-of-subjugation",
        "staff",
        "prayer-beads",
        "wind-tunnel-seal",
        "hiraikotsu",
        "arrow",
        "quiver",
        "backpack",
        "medical-kit",
        "sword",
        "staff-of-two-heads",
        "hammer",
        "harness",
        "fan",
        "feather",
        "horse",
        "mask",
        "eyepatch",
        "travel-pack",
        "walking-stick",
        "spear",
    },
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
    "background": {
        "minimal",
        "nature",
        "architecture",
        "night",
        "interior",
        "courtyard",
        "shrine",
        "graveyard",
    },
    "effect-type": {
        "none",
        "wind",
        "rain",
        "mist",
        "snow",
        "snow-light",
        "snow-heavy",
        "speed-lines",
        "impact",
        "aura",
        "wind-tunnel",
        "fox-fire",
        "transformation",
    },
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
        "weapon-construction",
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
    "prop-attachment": {"none", "waist", "back", "hand", "shoulder", "clothing", "body"},
    "costume-state": {"without-fire-rat-robe"},
    "perspective-risk": {"low", "medium", "high"},
    "scene-economy": {
        "authored-negative-space",
        "selective-detail",
        "dense-functional",
    },
    "detail-falloff": {"strong", "moderate", "flat"},
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


def parse_identity_facet(value: str) -> tuple[str, str, str]:
    subject, equals, remainder = value.partition("=")
    form, colon, facet = remainder.partition(":")
    if (
        not equals
        or not colon
        or not subject.strip()
        or form not in FORM_VALUES
        or facet not in OFFICIAL_IDENTITY_FACETS
    ):
        raise argparse.ArgumentTypeError(
            "identity facet must look like SUBJECT=FORM:FACET"
        )
    return subject.strip(), form, facet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--tags", nargs="+", default=[])
    parser.add_argument("--trait", type=parse_trait, action="append", default=[])
    parser.add_argument(
        "--identity-facet",
        type=parse_identity_facet,
        action="append",
        default=[],
        help="Bind one construction facet to an exact subject/form on this item.",
    )
    parser.add_argument("--note", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.tags and not args.trait and not args.identity_facet and not args.note:
        raise SystemExit(
            "Provide --tags, --trait, --identity-facet, --note, or a combination"
        )
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    paths = workflow_paths(root)
    if not paths["database"].is_file():
        raise SystemExit("Catalog missing; run build_reference_index.py first")
    connection = open_database(paths["database"], read_only=True)
    resolved = connection.execute(
        """
        SELECT item_id, subject_forms FROM items WHERE item_id = ?
        UNION ALL
        SELECT items.item_id, items.subject_forms FROM item_aliases
        JOIN items ON items.item_id = item_aliases.item_id
        WHERE item_aliases.alias_id = ?
        LIMIT 1
        """,
        (args.item_id, args.item_id),
    ).fetchone()
    if resolved is None:
        connection.close()
        raise SystemExit(f"Unknown catalog item: {args.item_id}")
    subject_forms = json.loads(resolved["subject_forms"] or "{}")
    facet_tags = []
    for subject, form, facet in args.identity_facet:
        if form not in subject_forms.get(subject, []):
            connection.close()
            raise SystemExit(
                f"Item does not contain exact subject/form {subject}={form}"
            )
        facet_tags.append(identity_facet_tag(subject, form, facet))
    connection.close()
    canonical_item_id = resolved["item_id"]
    annotations = paths["annotations"]
    annotations.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "item_id": canonical_item_id,
        "tags": sorted(set(args.tags) | set(args.trait) | set(facet_tags)),
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
