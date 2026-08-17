#!/usr/bin/env python3
"""Copy selected catalog images into an ordered task reference set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from image_sheet import build_contact_sheet
from task_workflow import is_split_domain_task
from workflow_common import (
    atomic_write_json,
    atomic_write_text,
    find_executable,
    load_config,
    open_database,
    resolve_recorded_path,
    workflow_paths,
    workflow_root,
)

ALLOWED_ROLES = {
    "target",
    "style",
    "identity",
    "form",
    "composition",
    "continuity",
    "content",
}
IDENTITY_CARD_RECIPES = (
    Path(__file__).resolve().parent.parent / "references" / "identity-card-recipes.json"
)
ROLE_ORDER = {
    "target": 0,
    "style": 1,
    "identity": 2,
    "form": 3,
    "continuity": 4,
    "composition": 5,
    "content": 6,
}
MANGA_CHARACTER_STYLE_INSTRUCTION = (
    "Control only selected-medium black-and-white manga character rendering: character "
    "contour rhythm and line hierarchy; face, hair, fabric, and fold mark-making; "
    "the relative paper-white, flat-black, and restrained halftone hierarchy used "
    "to separate the canonical garment parts defined by official identity evidence; "
    "effect construction. Do not alter or copy visible "
    "character identity, garment construction, components, patterns, or accessories, "
    "dialogue, balloons, panel borders, layout, pose, composition, or story content."
)
MANGA_SCENE_STYLE_INSTRUCTION = (
    "Control only selected-medium black-and-white manga scene rendering: architecture "
    "and natural-material mark grouping, paper-white and black-mass balance, restrained "
    "halftone, weather effects, background omission, negative space, and distance-based "
    "detail falloff. Treat its visible scene density as a ceiling, not a completeness "
    "target. Never transfer its texture frequency, contour density, black coverage, or "
    "lighting finish onto character faces, hair, costumes, or bodies. Do not copy visible "
    "people, poses, actions, framing, dialogue, balloons, panel borders, or story content; "
    "do not redefine canonical scene geometry."
)
MANGA_LEGACY_STYLE_INSTRUCTION = (
    "Control only selected-medium black-and-white manga rendering: character "
    "contour rhythm and line hierarchy; face, hair, fabric, and fold mark-making; "
    "the relative paper-white, flat-black, and restrained halftone garment value "
    "hierarchy; effect construction; background omission; material "
    "simplification; negative space; and distance-based detail falloff. Do not "
    "alter or copy identity, garment construction, dialogue, layout, pose, "
    "composition, or story content."
)
TV_STYLE_INSTRUCTION = (
    "Control only TV-series rendering: palette relationships, contour weight, face, "
    "hair, fabric, and fold treatment, cel-shadow shapes, relative garment value "
    "hierarchy, effect language, background softness, and shot-specific detail density. "
    "Do not alter or copy visible character identity, garment construction, components, "
    "patterns, or accessories, pose, framing, or story content."
)
IDENTITY_INSTRUCTION = (
    "Control canonical character identity, form, anatomy, costume components and "
    "layering, weapon or prop construction, attachment, and scale only. Do not "
    "control selected-medium mark-making, garment value or tone rendering, or scene "
    "composition. Treat this as a construction diagram, not a finish reference: "
    "redraw visible contours, face and hair marks, fabric lines, black areas, and "
    "values under the selected-medium character-style authority. Do not inherit "
    "uninspected finish traits from the identity sheet."
)
FORM_INSTRUCTION = (
    "Control only the exact requested form or age state visible in this selected-medium "
    "original: age-specific proportions, silhouette, face construction, hair-to-ear "
    "relationship, and form-specific garment scale. Do not control general character "
    "identity beyond visible form evidence, rendering style, palette, scene composition, "
    "or story content."
)
CONTINUITY_INSTRUCTION = (
    "Control only the user's selected visual continuity and proven finish quality. "
    "Do not override official identity, the selected medium's rendering grammar, or the new composition."
)
CONTENT_INSTRUCTION = (
    "Control only the exact visible content named by Exact focus: the requested "
    "action state, object or creature configuration, effect phase, or necessary "
    "spatial relationship. Do not control named-character identity, form, costume, "
    "palette, rendering style, camera framing, background treatment, or story staging."
)
CANONICAL_SCENE_IDENTITY_INSTRUCTION = (
    "Control only the exact canonical scene named by Exact focus: its identifying "
    "structure, fixed spatial relationships, and landmark proportions. Do not control or "
    "copy visible characters, poses, actions, expressions, dialogue, panel layout, "
    "or camera framing. ImageGen supplies the requested moment and staging."
)
CANONICAL_SCENE_STYLE_COVERAGE_INSTRUCTION = (
    " Human inspection recorded scene-style coverage as HIT, so this same source "
    "may also control selected-medium scene materials, weather treatment, negative "
    "space, black-white mass, and distance-based detail falloff."
)


def parse_selection(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("selection must look like ROLE=ITEM_ID")
    role, item_id = value.split("=", 1)
    if role not in ALLOWED_ROLES:
        raise argparse.ArgumentTypeError(f"unknown role: {role}")
    if not item_id:
        raise argparse.ArgumentTypeError("item id cannot be empty")
    return role, item_id


def parse_identity_card(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "identity card must look like CHARACTER=FORM"
        )
    character, form = (part.strip() for part in value.split("=", 1))
    if not character or not form:
        raise argparse.ArgumentTypeError(
            "identity card must look like CHARACTER=FORM"
        )
    return character, form


def parse_crop(value: str) -> tuple[str, tuple[int, int, int, int]]:
    item_id, separator, coordinates = value.partition("=")
    if not separator or not item_id:
        raise argparse.ArgumentTypeError("crop must look like ITEM_ID=X,Y,WIDTH,HEIGHT")
    try:
        crop_box = tuple(int(part.strip()) for part in coordinates.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("crop coordinates must be integers") from exc
    if len(crop_box) != 4:
        raise argparse.ArgumentTypeError("crop must contain X,Y,WIDTH,HEIGHT")
    validate_crop_box(crop_box)
    return item_id, crop_box


def parse_box(value: str) -> tuple[int, int, int, int]:
    try:
        box = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("box coordinates must be integers") from exc
    if len(box) != 4:
        raise argparse.ArgumentTypeError("box must look like X,Y,WIDTH,HEIGHT")
    validate_crop_box(box)
    return box


def parse_focus(value: str) -> tuple[str, str]:
    item_id, separator, focus = value.partition("=")
    if not separator or not item_id or not focus.strip():
        raise argparse.ArgumentTypeError("focus must look like ITEM_ID=VISIBLE_DETAIL")
    return item_id, focus.strip()


def parse_scene_style_coverage(value: str) -> tuple[str, str]:
    item_id, separator, status = value.partition("=")
    status = status.strip().upper()
    if not separator or not item_id or status not in {"HIT", "INSUFFICIENT"}:
        raise argparse.ArgumentTypeError(
            "scene style coverage must look like ITEM_ID=HIT|INSUFFICIENT"
        )
    return item_id, status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--select", type=parse_selection, action="append", default=[])
    parser.add_argument(
        "--identity-card",
        type=parse_identity_card,
        action="append",
        default=[],
        metavar="CHARACTER=FORM",
        help=(
            "Retired compatibility option. New generation inputs must use a "
            "shot-matched official setting sheet or focused official crop."
        ),
    )
    parser.add_argument(
        "--crop",
        type=parse_crop,
        action="append",
        default=[],
        metavar="ITEM_ID=X,Y,WIDTH,HEIGHT",
        help="Prepare a task-local crop from a newly selected catalog image.",
    )
    parser.add_argument(
        "--focus",
        type=parse_focus,
        action="append",
        default=[],
        metavar="ITEM_ID=VISIBLE_DETAIL",
        help="State the exact visible construction a selected reference may control.",
    )
    parser.add_argument(
        "--scene-style-coverage",
        type=parse_scene_style_coverage,
        action="append",
        default=[],
        metavar="ITEM_ID=HIT|INSUFFICIENT",
        help=(
            "Required for a canonical scene reference. HIT lets that image also "
            "cover scene rendering; INSUFFICIENT requires a separate scene style."
        ),
    )
    parser.add_argument(
        "--external",
        type=parse_selection,
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help="Add a user-supplied target or composition image without global indexing.",
    )
    parser.add_argument(
        "--external-target-crop",
        type=parse_box,
        metavar="X,Y,WIDTH,HEIGHT",
        help=(
            "Prepare only this context crop from the one external target. Use for "
            "a crop-and-composite microfix, not a whole-canvas edit."
        ),
    )
    parser.add_argument(
        "--external-target-focus",
        default="",
        help="Name the exact local change controlled by --external-target-crop.",
    )
    parser.add_argument(
        "--external-target-max-edge",
        type=int,
        metavar="PIXELS",
        help=(
            "Prepare a downscaled JPEG transport proxy for a full-canvas external "
            "target while retaining the original file and hash as provenance."
        ),
    )
    parser.add_argument(
        "--external-target-jpeg-quality",
        type=int,
        default=88,
        metavar="1-95",
        help="JPEG quality for --external-target-max-edge (default: 88).",
    )
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--columns", type=int, default=2)
    return parser.parse_args()


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_identity_card(
    root: Path, character: str, form: str
) -> tuple[dict[str, Any], Path]:
    manifest_path = root / "identity-cards" / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            "identity card manifest is missing; run build_identity_cards.py first"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not IDENTITY_CARD_RECIPES.is_file()
        or manifest.get("recipe_sha256") != file_hash(IDENTITY_CARD_RECIPES)
    ):
        raise ValueError(
            "identity card recipes changed; run build_identity_cards.py first"
        )
    matches = [
        card
        for card in manifest.get("cards", [])
        if card.get("character") == character and card.get("form") == form
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one identity card for {character}={form}; found {len(matches)}"
        )
    card = matches[0]
    output = root / "identity-cards" / str(card.get("output_file", ""))
    if not output.is_file() or file_hash(output) != card.get("output_sha256"):
        raise ValueError(f"identity card is missing or stale: {character}={form}")
    if not card.get("panels") or not all(
        panel.get("item_id") and panel.get("source_sha256")
        for panel in card["panels"]
    ):
        raise ValueError(f"identity card provenance is incomplete: {character}={form}")
    database = workflow_paths(root)["database"]
    connection = open_database(database, read_only=True)
    try:
        for panel in card["panels"]:
            row = connection.execute(
                "SELECT content_hash FROM items WHERE item_id = ?",
                (panel["item_id"],),
            ).fetchone()
            if row is None or row["content_hash"] != panel["source_sha256"]:
                raise ValueError(
                    f"identity card source is missing or stale: {panel['item_id']}"
                )
    finally:
        connection.close()
    return card, output


def validate_identity_card_reference(
    root: Path, entry: dict[str, Any], identity_forms: dict[str, str]
) -> tuple[str, str]:
    character = str(entry.get("character", ""))
    form = str(entry.get("form", ""))
    card, output = resolve_identity_card(root, character, form)
    expected_item_id = f"identity-card:{card['id']}"
    if entry.get("item_id") != expected_item_id:
        raise ValueError(f"identity card item id mismatch: {entry.get('item_id')}")
    if identity_forms.get(character) != form:
        raise ValueError(
            f"identity card {expected_item_id} does not match brief identity form"
        )
    if entry.get("content_hash") != card.get("output_sha256"):
        raise ValueError(f"identity card manifest hash mismatch: {expected_item_id}")
    if entry.get("card_id") != card.get("id"):
        raise ValueError(f"identity card id mismatch: {expected_item_id}")
    expected_subject_kind = card.get("subject_kind", "character")
    if entry.get("subject_kind", "character") != expected_subject_kind:
        raise ValueError(f"identity card subject kind mismatch: {expected_item_id}")
    if entry.get("source_authority") != card.get("authority"):
        raise ValueError(f"identity card authority mismatch: {expected_item_id}")
    expected_item_ids = list(
        dict.fromkeys(panel["item_id"] for panel in card["panels"])
    )
    expected_hashes = list(
        dict.fromkeys(panel["source_sha256"] for panel in card["panels"])
    )
    if entry.get("source_item_ids") != expected_item_ids:
        raise ValueError(f"identity card source ids mismatch: {expected_item_id}")
    if entry.get("source_hashes") != expected_hashes:
        raise ValueError(f"identity card source hashes mismatch: {expected_item_id}")
    rendered = resolve_recorded_path(entry.get("rendered_path", ""))
    if rendered != output.resolve() or file_hash(rendered) != card.get("output_sha256"):
        raise ValueError(f"identity card rendered path is stale: {expected_item_id}")
    return expected_item_id, character


def image_pixel_hash(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as image:
        image.load()
        digest = hashlib.sha256()
        digest.update(image.mode.encode("utf-8"))
        digest.update(f"{image.width}x{image.height}".encode("ascii"))
        digest.update(image.tobytes())
        return digest.hexdigest()


def source_crop_pixel_hash(source: Path, crop_box: tuple[int, int, int, int]) -> str:
    from PIL import Image

    with Image.open(source) as image:
        validate_crop_box(crop_box, image.size)
        x, y, width, height = crop_box
        cropped = image.crop((x, y, x + width, y + height))
        digest = hashlib.sha256()
        digest.update(cropped.mode.encode("utf-8"))
        digest.update(f"{cropped.width}x{cropped.height}".encode("ascii"))
        digest.update(cropped.tobytes())
        return digest.hexdigest()


def render_external_transport(
    source: Path,
    target: Path,
    max_edge: int,
    quality: int,
) -> dict[str, Any]:
    """Create a small upload proxy without replacing the source-of-truth target."""
    if max_edge < 256:
        raise ValueError("external target max edge must be at least 256 pixels")
    if quality < 1 or quality > 95:
        raise ValueError("external target JPEG quality must be between 1 and 95")

    from PIL import Image

    with Image.open(source) as image:
        image.load()
        source_dimensions = [image.width, image.height]
        converted = image.convert("RGBA")
        background = Image.new("RGBA", converted.size, "white")
        background.alpha_composite(converted)
        rendered = background.convert("RGB")
        rendered.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        rendered_dimensions = [rendered.width, rendered.height]
        rendered.save(target, format="JPEG", quality=quality, optimize=True)

    return {
        "kind": "downscaled-jpeg",
        "max_edge": max_edge,
        "quality": quality,
        "source_dimensions": source_dimensions,
        "rendered_dimensions": rendered_dimensions,
        "rendered_content_hash": file_hash(target),
    }


def validate_crop_box(
    crop_box: tuple[int, int, int, int],
    image_size: tuple[int | None, int | None] | None = None,
) -> None:
    x, y, width, height = crop_box
    if min(x, y) < 0 or min(width, height) < 1:
        raise ValueError("crop coordinates must be non-negative with positive size")
    if image_size and all(value is not None for value in image_size):
        image_width, image_height = image_size
        if x + width > image_width or y + height > image_height:
            raise ValueError(
                f"crop {crop_box} exceeds image bounds {image_width}x{image_height}"
            )


def render_item(
    row,
    role: str,
    output: Path,
    dpi: int,
    crop_box: tuple[int, int, int, int] | None = None,
) -> Path:
    if crop_box is not None:
        if row["kind"] != "image":
            raise ValueError(
                "Task-local crops currently require a catalog image source"
            )
        full_image = Path(row["path"])
        x, y, width, height = crop_box
        target = output / (
            f"{role}-{safe_name(row['item_id'])}-crop-{x}-{y}-{width}-{height}.png"
        )
        from PIL import Image

        with Image.open(full_image) as image:
            validate_crop_box(crop_box, image.size)
            cropped = image.crop((x, y, x + width, y + height))
            cropped.save(target, format="PNG")
        return target

    suffix = ".jpg" if row["kind"] == "pdf_page" else Path(row["path"]).suffix.lower()
    target = output / f"{role}-{safe_name(row['item_id'])}{suffix}"
    if target.exists():
        return target
    if row["kind"] == "image":
        shutil.copy2(row["path"], target)
        return target
    if row["kind"] != "pdf_page":
        raise ValueError(f"Cannot prepare item kind {row['kind']}; select an image")
    pdftoppm = find_executable("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm is required")
    prefix = target.with_suffix("")
    subprocess.run(
        [
            pdftoppm,
            "-f",
            str(row["pdf_page"]),
            "-l",
            str(row["pdf_page"]),
            "-singlefile",
            "-jpeg",
            "-r",
            str(dpi),
            "-jpegopt",
            "quality=92",
            row["path"],
            str(prefix),
        ],
        check=True,
    )
    if not target.is_file():
        raise RuntimeError(f"Renderer did not create {target}")
    return target


def instruction_for(
    role: str,
    medium: str,
    crop_box: tuple[int, int, int, int] | None = None,
    focus: str = "",
    source_medium: str | None = None,
    content_provenance: str = "observed-content",
    reference_domain: str = "",
    content_kind: str = "content",
    scene_style_coverage: str = "",
) -> str:
    if role == "identity":
        instruction = IDENTITY_INSTRUCTION
    elif role == "form":
        instruction = FORM_INSTRUCTION
    elif role == "style":
        if medium == "manga" and reference_domain == "scene":
            instruction = MANGA_SCENE_STYLE_INSTRUCTION
        elif medium == "manga" and reference_domain == "character-style":
            instruction = MANGA_CHARACTER_STYLE_INSTRUCTION
        elif medium == "manga":
            instruction = MANGA_LEGACY_STYLE_INSTRUCTION
        else:
            instruction = TV_STYLE_INSTRUCTION
    elif role == "continuity":
        instruction = CONTINUITY_INSTRUCTION
    elif role == "content":
        if not focus:
            raise ValueError("Content references require an exact focus")
        if content_kind == "scene":
            instruction = CANONICAL_SCENE_IDENTITY_INSTRUCTION
            if scene_style_coverage == "HIT":
                instruction += CANONICAL_SCENE_STYLE_COVERAGE_INSTRUCTION
            elif scene_style_coverage != "INSUFFICIENT":
                raise ValueError(
                    "Canonical scene references require scene style coverage HIT or INSUFFICIENT"
                )
        else:
            instruction = CONTENT_INSTRUCTION
        if source_medium and source_medium != medium:
            instruction += (
                f" This is cross-medium {source_medium}-to-{medium} content evidence. "
                f"Ignore all {source_medium} palette, contour, shading, texture, and "
                f"background grammar; translate only the named content into the {medium} "
                "rendering established by the style reference."
            )
        if content_provenance == "fallback-medium-original":
            if not source_medium or source_medium == medium:
                raise ValueError(
                    "fallback-medium-original provenance requires cross-medium content"
                )
            instruction += (
                " This design is explicitly original to the fallback medium; label "
                "the result as a source-medium-derived adaptation and do not present "
                "it as selected-medium canonical evidence."
            )
    else:
        instruction = ""
    if crop_box is not None:
        instruction += (
            f" This prepared image is a task-local crop {crop_box} from the recorded "
            "source; use only construction visible inside the crop and do not infer "
            "omitted states."
        )
    if focus:
        instruction += f" Exact focus: {focus}"
    return instruction.strip()


def json_values(row, field: str) -> set[str]:
    return set(json.loads(row[field] or "[]"))


def json_object(row, field: str) -> dict[str, list[str]]:
    if hasattr(row, "keys") and field not in row:
        return {}
    return json.loads(row[field] or "{}")


def validate_reference(
    row,
    role: str,
    item_id: str,
    medium: str,
    identity_forms: dict[str, str],
    *,
    crop_box: tuple[int, int, int, int] | None = None,
    focus: str = "",
) -> None:
    if role not in ALLOWED_ROLES:
        raise SystemExit(f"Unknown reference role in manifest: {role}")

    source_id = row["source_id"]
    manifest_to_evidence_role = {"style": "rendering", "form": "rendering"}
    required_role = manifest_to_evidence_role.get(role, role)
    has_eligible_roles = hasattr(row, "keys") and "eligible_roles" in row
    eligible_roles = json_values(row, "eligible_roles") if has_eligible_roles else set()
    if has_eligible_roles and required_role not in eligible_roles:
        raise SystemExit(
            f"Reference is not eligible for role {role}: {item_id}; "
            f"eligible roles={sorted(eligible_roles)}"
        )
    if role == "identity" and source_id != "official":
        raise SystemExit(
            f"Identity references must come from official setting sheets: {item_id}"
        )
    if role == "form":
        expected_source = "manga-curated" if medium == "manga" else "tv-curated"
        if source_id != expected_source:
            raise SystemExit(
                f"{medium} form references must come from {expected_source}: {item_id}"
            )
    if role == "style":
        try:
            domain = row["reference_domain"]
        except (IndexError, KeyError):
            domain = ""
        if domain not in {"character-style", "scene", ""}:
            raise SystemExit(
                f"Style references must come from a style domain, not {domain}: {item_id}"
            )
        expected_source = "manga-curated" if medium == "manga" else "tv-curated"
        if source_id != expected_source:
            raise SystemExit(
                f"{medium} style references must come from {expected_source}: {item_id}"
            )
    if role == "target" and source_id != "user-continuity":
        raise SystemExit(f"Target references must come from user-continuity: {item_id}")
    if role == "continuity" and source_id not in {
        "selected-output",
        "user-continuity",
    }:
        raise SystemExit(
            "Continuity references must come from selected-output or user-continuity: "
            f"{item_id}"
        )
    if role == "composition" and source_id != "user-continuity":
        raise SystemExit(f"Composition references must be user-supplied: {item_id}")
    if role == "content" and source_id not in {"manga-curated", "tv-curated"}:
        raise SystemExit(
            f"Content references must come from manga-curated or tv-curated: {item_id}"
        )

    # Style evidence controls mark-making only. Visible characters or forms in
    # that screenshot must not become an identity gate for the target task.
    if role == "style":
        return
    if not identity_forms:
        return
    subjects = json_values(row, "subjects")
    forms = json_values(row, "forms")
    subject_forms = json_object(row, "subject_forms")
    matching_subjects = subjects & set(identity_forms)
    if role in {"identity", "form"} and not matching_subjects:
        raise SystemExit(
            f"{role.title()} reference does not name any requested character: "
            f"{item_id}; indexed subjects={sorted(subjects) or ['unclassified']}"
        )
    for subject in sorted(matching_subjects):
        required_form = identity_forms[subject]
        compatible_forms = set(subject_forms.get(subject, [])) or forms
        if required_form not in compatible_forms:
            if role == "content" and crop_box is not None and focus.strip():
                continue
            indexed = sorted(compatible_forms) or ["unclassified"]
            raise SystemExit(
                "Form-incompatible reference rejected: "
                f"{item_id} depicts {subject} as {indexed}, "
                f"but this task requires {required_form}"
            )


def validate_reference_order(references: list[tuple[str, str]]) -> None:
    roles = [role for role, _ in references]
    if roles.count("target") > 1:
        raise SystemExit("Use at most one target reference")
    if roles.count("continuity") > 1:
        raise SystemExit("Use at most one selected-output continuity reference")
    if roles.count("content") > 1:
        raise SystemExit("Use at most one exact-focus content reference")
    if "target" in roles and roles[0] != "target":
        raise SystemExit("A target reference must be first")
    ranks = [ROLE_ORDER[role] for role in roles]
    if ranks != sorted(ranks):
        raise SystemExit(
            "Reference order must be target, style, identity, form, continuity, composition, content"
        )


def main() -> int:
    args = parse_args()
    if args.identity_card:
        raise SystemExit(
            "Identity cards are retired from generation inputs; select a current "
            "official setting-sheet item with --select identity=ITEM_ID and use "
            "--crop/--focus when the shot needs a focused detail."
        )
    if args.dpi < 72 or args.dpi > 300:
        raise SystemExit("--dpi must be between 72 and 300")
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    database = workflow_paths(root)["database"]

    task_dir = args.task_dir.expanduser().resolve()
    brief_path = task_dir / "brief.json"
    if not task_dir.is_dir() or not brief_path.is_file():
        raise SystemExit("--task-dir must be a task created by init_art_task.py")
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    qa_path = task_dir / "qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8")) if qa_path.is_file() else {}
    split_domain_task = is_split_domain_task(brief, qa)
    medium = brief.get("medium")
    identity_forms = brief.get("identity_forms", {})
    prop_forms = brief.get("prop_forms", {})
    required_forms = {**identity_forms, **prop_forms}
    content_need = brief.get("content_need") or {}
    content_provenance = content_need.get("provenance", "observed-content")
    content_kind = content_need.get("kind", "content")

    output = task_dir / "references"
    output.mkdir(exist_ok=True)
    manifest_path = task_dir / "reference-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog_required = bool(
        args.select
        or args.crop
        or args.focus
        or any(
            entry.get("source_id") != "user-supplied"
            for entry in manifest.get("references", [])
        )
    )
    if catalog_required and not database.is_file():
        raise SystemExit("Catalog missing; run build_reference_index.py first")
    connection = (
        open_database(database, read_only=True)
        if database.is_file()
        else sqlite3.connect(":memory:")
    )

    requested_cards: list[tuple[dict[str, Any], Path]] = []
    seen_card_characters: set[str] = set()
    for character, form in args.identity_card:
        if identity_forms.get(character) != form:
            connection.close()
            raise SystemExit(
                f"Identity card does not match brief: {character}={form}"
            )
        if character in seen_card_characters:
            connection.close()
            raise SystemExit(f"Duplicate identity card character: {character}")
        try:
            requested_cards.append(resolve_identity_card(root, character, form))
        except ValueError as exc:
            connection.close()
            raise SystemExit(str(exc)) from exc
        seen_card_characters.add(character)

    def resolve_item(item_id: str):
        return connection.execute(
            """
            SELECT items.*, sources.label AS source_label, sources.medium
            FROM items JOIN sources ON sources.source_id = items.source_id
            WHERE items.item_id = ? OR items.item_id = (
                SELECT aliases.item_id FROM item_aliases AS aliases
                WHERE aliases.alias_id = ?
            )
            """,
            (item_id, item_id),
        ).fetchone()

    def canonical_assignments(
        values: list[tuple[str, Any]], label: str
    ) -> dict[str, Any]:
        assignments: dict[str, Any] = {}
        for requested_id, value in values:
            row = resolve_item(requested_id)
            if row is None:
                connection.close()
                raise SystemExit(f"Unknown catalog item in --{label}: {requested_id}")
            canonical_id = row["item_id"]
            if canonical_id in assignments:
                connection.close()
                raise SystemExit(
                    f"Duplicate --{label} for catalog item: {requested_id}"
                )
            assignments[canonical_id] = value
        return assignments

    crop_requests = canonical_assignments(args.crop, "crop")
    focus_requests = canonical_assignments(args.focus, "focus")
    scene_style_coverage_requests = canonical_assignments(
        args.scene_style_coverage, "scene-style-coverage"
    )
    if set(crop_requests) - set(focus_requests):
        connection.close()
        missing = sorted(set(crop_requests) - set(focus_requests))
        raise SystemExit(f"Every --crop requires a matching --focus: {missing}")

    existing_canonical: dict[str, tuple[str, str]] = {}
    existing_card_characters: set[str] = set()
    existing_official_identity_subjects: set[str] = set()
    all_references = []
    for entry in manifest.get("references", []):
        item_id = entry.get("item_id", "")
        role = entry.get("role", "")
        if entry.get("source_id") == "identity-card":
            try:
                canonical_id, character = validate_identity_card_reference(
                    root, entry, identity_forms
                )
            except ValueError as exc:
                connection.close()
                raise SystemExit(str(exc)) from exc
            if canonical_id in existing_canonical:
                connection.close()
                raise SystemExit(f"Duplicate identity card in manifest: {canonical_id}")
            existing_canonical[canonical_id] = (role, canonical_id)
            existing_card_characters.add(character)
            all_references.append((role, canonical_id))
            continue
        if entry.get("source_id") == "user-supplied":
            if role not in {"target", "composition"}:
                connection.close()
                raise SystemExit(f"Unsupported user-supplied role: {role}")
            if item_id in existing_canonical:
                connection.close()
                raise SystemExit(f"Duplicate user-supplied item: {item_id}")
            existing_canonical[item_id] = (role, item_id)
            all_references.append((role, item_id))
            continue
        existing_row = resolve_item(item_id)
        if existing_row is None:
            connection.close()
            raise SystemExit(
                f"Unknown catalog item in manifest: {item_id or '[missing]'}"
            )
        canonical_id = existing_row["item_id"]
        if canonical_id in existing_canonical:
            connection.close()
            raise SystemExit(f"Duplicate catalog item in manifest: {item_id}")
        validate_reference(
            existing_row,
            role,
            item_id,
            medium,
            required_forms,
            crop_box=tuple(entry["crop_box"]) if entry.get("crop_box") else None,
            focus=entry.get("focus", ""),
        )
        if role == "content":
            focus = entry.get("focus", "").strip()
            if not focus:
                connection.close()
                raise SystemExit(
                    f"Content reference requires an exact focus: {item_id}"
                )
            if focus != content_need.get("focus"):
                connection.close()
                raise SystemExit(
                    "Content reference focus must match brief.content_need.focus: "
                    f"{item_id}"
                )
            if content_kind == "scene":
                try:
                    domain = existing_row["reference_domain"]
                except (IndexError, KeyError):
                    domain = ""
                expected_source = (
                    "manga-curated" if medium == "manga" else "tv-curated"
                )
                if domain != "scene" or existing_row["source_id"] != expected_source:
                    connection.close()
                    raise SystemExit(
                        "Canonical scene evidence must come from the selected-medium "
                        f"scene domain: {item_id}"
                    )
                if entry.get("scene_style_coverage") not in {"HIT", "INSUFFICIENT"}:
                    connection.close()
                    raise SystemExit(
                        "Canonical scene manifest entries require "
                        f"scene_style_coverage HIT or INSUFFICIENT: {item_id}"
                    )
        existing_canonical[canonical_id] = (role, item_id)
        if role == "identity":
            existing_official_identity_subjects.update(
                json.loads(existing_row["subjects"] or "[]")
            )
        all_references.append((role, canonical_id))

    duplicate_existing_identity = (
        existing_card_characters & existing_official_identity_subjects
    )
    if duplicate_existing_identity:
        connection.close()
        raise SystemExit(
            "Use either the identity card or an official identity image for "
            f"{sorted(duplicate_existing_identity)}, not both"
        )

    canonical_roles = {
        canonical_id: role for canonical_id, (role, _) in existing_canonical.items()
    }
    external_target_rows = []
    external_composition_rows = []
    for role, path_text in args.external:
        if role not in {"target", "composition"}:
            connection.close()
            raise SystemExit("--external supports target or composition images only")
        source = Path(path_text).expanduser().resolve()
        if not source.is_file():
            connection.close()
            raise SystemExit(f"External {role} image is missing: {source}")
        content_hash = file_hash(source)
        item_id = f"user-supplied:file:{content_hash[:20]}"
        if item_id in canonical_roles:
            if canonical_roles[item_id] != role:
                connection.close()
                raise SystemExit(
                    f"User-supplied image already has role {canonical_roles[item_id]}, "
                    f"not {role}: {source}"
                )
            continue
        row = (role, item_id, source, content_hash)
        if role == "target":
            external_target_rows.append(row)
        else:
            external_composition_rows.append(row)

    if args.external_target_crop and len(external_target_rows) != 1:
        connection.close()
        raise SystemExit(
            "--external-target-crop requires exactly one newly added external target"
        )
    if args.external_target_crop and not args.external_target_focus.strip():
        connection.close()
        raise SystemExit("--external-target-crop requires --external-target-focus")
    if args.external_target_crop and args.external_target_max_edge:
        connection.close()
        raise SystemExit(
            "--external-target-max-edge cannot be combined with --external-target-crop"
        )
    if args.external_target_max_edge and len(external_target_rows) != 1:
        connection.close()
        raise SystemExit(
            "--external-target-max-edge requires exactly one newly added external target"
        )

    if external_target_rows and all_references:
        connection.close()
        raise SystemExit("Add the external target before any other task references")
    for role, item_id, source, content_hash in external_target_rows:
        canonical_roles[item_id] = role
        all_references.append((role, item_id))

    selected_rows = []
    selected_canonical_ids = set()
    for role, item_id in args.select:
        row = resolve_item(item_id)
        if row is None:
            connection.close()
            raise SystemExit(f"Unknown catalog item: {item_id}")
        canonical_id = row["item_id"]
        if canonical_id in canonical_roles:
            existing_role = canonical_roles[canonical_id]
            if existing_role != role:
                connection.close()
                raise SystemExit(
                    f"Reference already has role {existing_role}, not {role}: {item_id}"
                )
            continue
        focus = focus_requests.get(canonical_id, "")
        crop_box = crop_requests.get(canonical_id)
        scene_style_coverage = scene_style_coverage_requests.get(canonical_id, "")
        validate_reference(
            row,
            role,
            item_id,
            medium,
            required_forms,
            crop_box=crop_box,
            focus=focus,
        )
        if role == "content":
            if not focus:
                connection.close()
                raise SystemExit(
                    f"Content reference requires --focus {canonical_id}=VISIBLE_CONTENT"
                )
            if not content_need.get("focus"):
                connection.close()
                raise SystemExit(
                    "Plan exact content retrieval before selection; brief.content_need.focus is missing"
                )
            if focus != content_need.get("focus"):
                connection.close()
                raise SystemExit(
                    "--focus for a content reference must exactly match "
                    "brief.content_need.focus"
                )
            if content_kind == "scene":
                expected_source = (
                    "manga-curated" if medium == "manga" else "tv-curated"
                )
                if row["reference_domain"] != "scene" or row["source_id"] != expected_source:
                    connection.close()
                    raise SystemExit(
                        "Canonical scene evidence must come from the selected-medium "
                        f"scene domain: {item_id}"
                    )
                if scene_style_coverage not in {"HIT", "INSUFFICIENT"}:
                    connection.close()
                    raise SystemExit(
                        "Canonical scene selection requires --scene-style-coverage "
                        f"{canonical_id}=HIT|INSUFFICIENT"
                    )
        elif scene_style_coverage:
            connection.close()
            raise SystemExit(
                "--scene-style-coverage is valid only for a canonical scene content reference"
            )
        selected_rows.append(
            (
                role,
                canonical_id,
                row,
                crop_box,
                focus,
                scene_style_coverage,
            )
        )
        selected_canonical_ids.add(canonical_id)
        canonical_roles[canonical_id] = role
        all_references.append((role, canonical_id))

    unused_detail_requests = (
        set(crop_requests) | set(focus_requests)
        | set(scene_style_coverage_requests)
    ) - selected_canonical_ids
    if unused_detail_requests:
        connection.close()
        raise SystemExit(
            "--crop, --focus, and --scene-style-coverage must name references "
            "newly added with --select: "
            f"{sorted(unused_detail_requests)}"
        )

    for role, item_id, source, content_hash in external_composition_rows:
        if item_id in canonical_roles:
            connection.close()
            raise SystemExit(f"Duplicate external image role: {item_id}")
        canonical_roles[item_id] = role
        all_references.append((role, item_id))
    external_rows = [*external_target_rows, *external_composition_rows]
    card_rows = []
    selected_identity_subjects = {
        subject
        for role, _, row, _, _, _ in selected_rows
        if role == "identity"
        for subject in json.loads(row["subjects"] or "[]")
    }
    duplicate_selected_identity = existing_card_characters & selected_identity_subjects
    if duplicate_selected_identity:
        connection.close()
        raise SystemExit(
            "Use either the identity card or an official identity image for "
            f"{sorted(duplicate_selected_identity)}, not both"
        )
    for card, card_path in requested_cards:
        item_id = f"identity-card:{card['id']}"
        if item_id in canonical_roles:
            continue
        if card["character"] in (
            selected_identity_subjects | existing_official_identity_subjects
        ):
            connection.close()
            raise SystemExit(
                "Use either the identity card or an official identity image for "
                f"{card['character']}, not both"
            )
        card_rows.append((card, card_path))
        canonical_roles[item_id] = "identity"
        all_references.append(("identity", item_id))
    validate_reference_order(all_references)
    connection.close()

    if (
        len(manifest.get("references", []))
        + len(selected_rows)
        + len(external_rows)
        + len(card_rows)
        > 6
    ):
        raise SystemExit(
            "Prepare at most six references total; two to four is the normal target"
        )

    current_style_ids = {
        canonical_id
        for canonical_id, (role, _) in existing_canonical.items()
        if role == "style"
    }
    requested_style_ids = current_style_ids | {
        item_id for role, item_id, _, _, _, _ in selected_rows if role == "style"
    }
    max_style_references = 3 if split_domain_task else 2
    if len(requested_style_ids) > max_style_references:
        raise SystemExit(
            f"Use at most {max_style_references} curated style screenshots per task"
        )
    if split_domain_task:
        existing_style_domains = [
            entry.get("reference_domain")
            for entry in manifest.get("references", [])
            if entry.get("role") == "style" and entry.get("reference_domain")
        ]
        selected_style_domains = [
            row["reference_domain"]
            for role, _, row, _, _, _ in selected_rows
            if role == "style"
        ]
        style_domains = existing_style_domains + selected_style_domains
        if style_domains.count("scene") > 1:
            raise SystemExit(
                "New split-domain tasks allow at most one scene-style reference"
            )
        if style_domains.count("character-style") > 2:
            raise SystemExit(
                "New split-domain tasks allow at most two character-style references"
            )

    added = []
    for role, item_id, source, content_hash in external_target_rows:
        crop_box = args.external_target_crop
        transport = None
        if crop_box is None and args.external_target_max_edge:
            target = output / f"{role}-{safe_name(item_id)}-transport.jpg"
            transport = render_external_transport(
                source,
                target,
                args.external_target_max_edge,
                args.external_target_jpeg_quality,
            )
        elif crop_box is None:
            target = output / f"{role}-{safe_name(item_id)}{source.suffix.lower()}"
            if not target.exists():
                shutil.copy2(source, target)
        else:
            x, y, width, height = crop_box
            target = output / (
                f"{role}-{safe_name(item_id)}-crop-{x}-{y}-{width}-{height}.png"
            )
            from PIL import Image

            with Image.open(source) as image:
                validate_crop_box(crop_box, image.size)
                image.crop((x, y, x + width, y + height)).save(target, format="PNG")
        entry = {
            "order": len(manifest.get("references", [])) + len(added) + 1,
            "role": role,
            "item_id": item_id,
            "source_id": "user-supplied",
            "source_authority": "edit-target",
            "content_hash": content_hash,
            "folder_path": "",
            "content_label": "",
            "folder_tags": [],
            "subjects": [],
            "forms": [],
            "subject_forms": {},
            "shot_types": [],
            "filename_terms": [],
            "rendered_path": str(target),
            "original_path": str(source),
            "pdf_page": None,
            "instructions": (
                (
                    "This is a context crop from the edit target. Change only "
                    f"{args.external_target_focus.strip()}; preserve crop-edge "
                    "continuity for deterministic compositing into the original."
                )
                if crop_box is not None
                else (
                    "Preserve this image exactly except for the user's explicitly "
                    "requested local edit."
                )
            ),
            "crop_box": list(crop_box) if crop_box is not None else None,
            "focus": args.external_target_focus.strip() if crop_box else "",
        }
        if transport is not None:
            entry["transport"] = transport
        if crop_box is not None:
            entry["rendered_content_hash"] = file_hash(target)
            entry["crop_source_hash"] = source_crop_pixel_hash(source, crop_box)
        added.append(entry)

    for card, card_path in card_rows:
        item_id = f"identity-card:{card['id']}"
        provenance_note = (
            " It is derived only from canonical official identity sources."
            if card.get("canonical_sources_only")
            else " It includes a user-directed derivative source and is not a "
            "publisher-original official image."
        )
        subject_kind = card.get("subject_kind", "character")
        subject_label = "named prop" if subject_kind == "prop" else "named character"
        added.append(
            {
                "order": len(manifest.get("references", [])) + len(added) + 1,
                "role": "identity",
                "item_id": item_id,
                "source_id": "identity-card",
                "source_authority": card["authority"],
                "content_hash": card["output_sha256"],
                "folder_path": "identity-cards",
                "content_label": card["id"],
                "folder_tags": ["identity-card"],
                "subjects": [card["character"]],
                "forms": [card["form"]],
                "subject_forms": {card["character"]: [card["form"]]},
                "shot_types": [],
                "filename_terms": [card["character"], card["form"]],
                "rendered_path": str(card_path.resolve()),
                "original_path": str(card_path.resolve()),
                "pdf_page": None,
                "instructions": (
                    f"Control only the {subject_label}'s canonical appearance, "
                    "construction, attachment, and scale. This "
                    "is a provenance-preserving transport bundle derived from the "
                    "recorded source panels; it does not control rendering style or "
                    f"scene composition.{provenance_note}"
                ),
                "crop_box": None,
                "focus": "",
                "character": card["character"],
                "form": card["form"],
                "card_id": card["id"],
                "subject_kind": subject_kind,
                "source_item_ids": list(
                    dict.fromkeys(panel["item_id"] for panel in card["panels"])
                ),
                "source_hashes": list(
                    dict.fromkeys(panel["source_sha256"] for panel in card["panels"])
                ),
            }
        )

    for role, item_id, row, crop_box, focus, scene_style_coverage in selected_rows:
        target = render_item(row, role, output, args.dpi, crop_box)
        entry = {
            "order": len(manifest.get("references", [])) + len(added) + 1,
            "role": role,
            "item_id": item_id,
            "source_id": row["source_id"],
            "reference_domain": row["reference_domain"],
            "source_authority": row["authority"],
            "content_hash": row["content_hash"],
            "folder_path": row["folder_path"],
            "content_label": row["content_label"],
            "folder_tags": json.loads(row["folder_tags"]),
            "subjects": json.loads(row["subjects"]),
            "forms": json.loads(row["forms"]),
            "subject_forms": json.loads(row["subject_forms"]),
            "shot_types": json.loads(row["shot_types"]),
            "filename_terms": json.loads(row["filename_terms"]),
            "rendered_path": str(target),
            "original_path": row["path"],
            "pdf_page": row["pdf_page"],
            "instructions": instruction_for(
                role,
                medium,
                crop_box,
                focus,
                source_medium=row["medium"],
                content_provenance=content_provenance,
                reference_domain=row["reference_domain"],
                content_kind=content_kind,
                scene_style_coverage=scene_style_coverage,
            ),
            "crop_box": list(crop_box) if crop_box is not None else None,
            "focus": focus,
        }
        if crop_box is not None:
            entry["rendered_content_hash"] = file_hash(target)
            entry["crop_source_hash"] = source_crop_pixel_hash(
                Path(row["path"]), crop_box
            )
        if role == "content":
            cross_medium = row["medium"] != medium
            entry["evidence_medium"] = row["medium"]
            entry["cross_medium"] = cross_medium
            entry["conversion"] = (
                f"{row['medium']}-to-{medium}-content" if cross_medium else None
            )
            entry["provenance"] = content_provenance
            entry["content_kind"] = content_kind
            if content_kind == "scene":
                entry["scene_style_coverage"] = scene_style_coverage
        if role == "style":
            entry["style_scope"] = (
                "scene" if row["reference_domain"] == "scene" else "character"
            )
        added.append(entry)

    for role, item_id, source, content_hash in external_composition_rows:
        target = output / f"{role}-{safe_name(item_id)}{source.suffix.lower()}"
        if not target.exists():
            shutil.copy2(source, target)
        added.append(
            {
                "order": len(manifest.get("references", [])) + len(added) + 1,
                "role": role,
                "item_id": item_id,
                "source_id": "user-supplied",
                "source_authority": "requested-composition",
                "content_hash": content_hash,
                "folder_path": "",
                "content_label": "",
                "folder_tags": [],
                "subjects": [],
                "forms": [],
                "subject_forms": {},
                "shot_types": [],
                "filename_terms": [],
                "rendered_path": str(target),
                "original_path": str(source),
                "pdf_page": None,
                "instructions": (
                    "Control only framing, crop, gaze direction, and broad silhouette. "
                    "Do not control character identity, form, costume, color, or rendering style."
                ),
            }
        )

    added.sort(key=lambda entry: ROLE_ORDER[entry["role"]])
    for index, entry in enumerate(
        added, start=len(manifest.get("references", [])) + 1
    ):
        entry["order"] = index
    manifest.setdefault("references", []).extend(added)
    atomic_write_json(manifest_path, manifest)
    brief["style_references"] = [
        entry["item_id"] for entry in manifest["references"] if entry["role"] == "style"
    ]
    brief["form_references"] = [
        entry["item_id"] for entry in manifest["references"] if entry["role"] == "form"
    ]
    brief["content_references"] = [
        entry["item_id"]
        for entry in manifest["references"]
        if entry["role"] == "content"
    ]
    scene_entries = [
        entry
        for entry in manifest["references"]
        if entry.get("role") == "content" and entry.get("content_kind") == "scene"
    ]
    brief["scene_style_coverage"] = (
        scene_entries[0].get("scene_style_coverage") if scene_entries else None
    )
    atomic_write_json(brief_path, brief)

    entries = [
        (
            resolve_recorded_path(entry["rendered_path"]),
            (
                f"{entry['order']}. {entry['role']} | {entry['source_id']} | "
                f"{entry['item_id'].rsplit(':', 1)[-1][-12:]}"
            ),
        )
        for entry in manifest["references"]
    ]
    contact_sheet = output / "contact-sheet.jpg"
    build_contact_sheet(entries, contact_sheet, columns=args.columns)
    lines = ["# Reference manifest", ""]
    for entry in manifest["references"]:
        locator = entry["original_path"]
        if entry["pdf_page"] and Path(locator).suffix.lower() == ".pdf":
            locator += f"#page={entry['pdf_page']}"
        lines.extend(
            [
                f"## Image {entry['order']}: {entry['role']}",
                "",
                f"- Item: `{entry['item_id']}`",
                f"- Authority: `{entry['source_authority']}`",
                f"- Reference domain: `{entry.get('reference_domain') or 'N/A'}`",
                f"- Style scope: `{entry.get('style_scope') or 'N/A'}`",
                f"- Scene style coverage: `{entry.get('scene_style_coverage') or 'N/A'}`",
                f"- Prepared file: `{entry['rendered_path']}`",
                f"- Source: `{locator}`",
                f"- Folder labels: `{', '.join(entry.get('folder_tags', [])) or 'N/A'}`",
                f"- Content label: `{entry.get('content_label') or 'N/A'}`",
                f"- Subjects: `{', '.join(entry.get('subjects', [])) or 'N/A'}`",
                f"- Forms: `{', '.join(entry.get('forms', [])) or 'N/A'}`",
                f"- Subject forms: `{json.dumps(entry.get('subject_forms', {}), ensure_ascii=False)}`",
                f"- Shot types: `{', '.join(entry.get('shot_types', [])) or 'N/A'}`",
                f"- Crop box: `{entry.get('crop_box') or 'N/A'}`",
                f"- Exact focus: `{entry.get('focus') or 'N/A'}`",
                f"- Prompt instruction: {entry['instructions'] or '[fill before generation]'}",
                "",
            ]
        )
    atomic_write_text(task_dir / "reference-manifest.md", "\n".join(lines))
    print(manifest_path)
    print(contact_sheet)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
