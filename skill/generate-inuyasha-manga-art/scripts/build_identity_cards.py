#!/usr/bin/env python3
"""Maintain retired identity-card artifacts for historical provenance only."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from workflow_common import (
    atomic_write_json,
    load_config,
    open_database,
    workflow_paths,
    workflow_root,
)

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RECIPES = SKILL_DIR / "references" / "identity-card-recipes.json"
CARD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_box(value: Any, label: str) -> tuple[int, int, int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not all(isinstance(item, int) for item in value)
    ):
        raise ValueError(f"{label} must contain four integers")
    x, y, width, height = value
    if x < 0 or y < 0 or width < 1 or height < 1:
        raise ValueError(f"{label} must use non-negative x/y and positive size")
    return x, y, width, height


def load_recipes(path: Path) -> dict[str, Any]:
    recipes = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if recipes.get("schema_version") != 1:
        raise ValueError("identity card recipes schema_version must be 1")
    cards = recipes.get("cards")
    if not isinstance(cards, list) or not cards:
        raise ValueError("identity card recipes require at least one card")
    seen: set[str] = set()
    for card in cards:
        card_id = str(card.get("id", "")).strip()
        if not card_id or card_id in seen:
            raise ValueError(f"invalid or duplicate identity card id: {card_id}")
        seen.add(card_id)
        if not str(card.get("character", "")).strip():
            raise ValueError(f"identity card {card_id} requires character")
        if not str(card.get("form", "")).strip():
            raise ValueError(f"identity card {card_id} requires form")
        subject_kind = str(card.get("subject_kind", "character")).strip()
        if subject_kind not in {"character", "prop"}:
            raise ValueError(
                f"identity card {card_id} subject_kind must be character or prop"
            )
        parse_box([0, 0, *card.get("canvas", [])], f"{card_id}.canvas")
        panels = card.get("panels")
        if not isinstance(panels, list) or not panels:
            raise ValueError(f"identity card {card_id} requires panels")
        for index, panel in enumerate(panels, 1):
            if not str(panel.get("item_id", "")).strip():
                raise ValueError(f"{card_id} panel {index} requires item_id")
            if not str(panel.get("source_relative_path", "")).strip():
                raise ValueError(
                    f"{card_id} panel {index} requires source_relative_path"
                )
            if not str(panel.get("focus", "")).strip():
                raise ValueError(f"{card_id} panel {index} requires focus")
            parse_box(panel.get("target_box"), f"{card_id}.panel{index}.target_box")
            if panel.get("crop_box") is not None:
                parse_box(panel["crop_box"], f"{card_id}.panel{index}.crop_box")
    return recipes


def resolve_panel(connection, panel: dict[str, Any], card: dict[str, Any]) -> dict:
    row = connection.execute(
        """
        SELECT items.*
        FROM items
        WHERE items.item_id = ? OR items.item_id = (
            SELECT item_id FROM item_aliases WHERE alias_id = ?
        )
        """,
        (panel["item_id"], panel["item_id"]),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown identity card item: {panel['item_id']}")
    if row["source_id"] != "official":
        raise ValueError(f"identity card source must be official: {row['item_id']}")
    if row["kind"] != "image":
        raise ValueError(f"identity card source must be an image: {row['item_id']}")
    if row["relative_path"] != panel["source_relative_path"]:
        raise ValueError(
            f"identity card source path mismatch for {row['item_id']}: "
            f"{row['relative_path']}"
        )
    subjects = set(json.loads(row["subjects"] or "[]"))
    forms = set(json.loads(row["forms"] or "[]"))
    subject_forms = json.loads(row["subject_forms"] or "{}")
    compatible = set(subject_forms.get(card["character"], [])) or forms
    if card["character"] not in subjects or card["form"] not in compatible:
        raise ValueError(
            f"identity card source {row['item_id']} is incompatible with "
            f"{card['character']}={card['form']}"
        )
    config = load_config()
    source_config = next(
        (
            source
            for source in config.get("sources", [])
            if source.get("id") == row["source_id"]
        ),
        None,
    )
    if source_config is None:
        raise ValueError(f"identity card source is unconfigured: {row['source_id']}")
    relative = Path(str(row["relative_path"]).replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(
            f"identity card source path is unsafe: {row['relative_path']}"
        )
    source_root = Path(source_config["path"]).resolve()
    source = source_root.joinpath(*relative.parts).resolve()
    if not source.is_relative_to(source_root):
        raise ValueError(
            f"identity card source escapes its configured root: {row['relative_path']}"
        )
    if not source.is_file():
        raise ValueError(f"identity card source is missing: {source}")
    actual_hash = file_hash(source)
    if actual_hash != row["content_hash"]:
        raise ValueError(f"identity card source changed since indexing: {source}")
    return {
        "item_id": row["item_id"],
        "source_id": row["source_id"],
        "source_authority": row["authority"],
        "source_path": source,
        "source_relative_path": row["relative_path"],
        "source_sha256": actual_hash,
        "source_dimensions": [row["width"], row["height"]],
        "focus": panel["focus"],
        "crop_box": panel.get("crop_box"),
        "target_box": panel["target_box"],
    }


def render_card(card: dict[str, Any], panels: list[dict[str, Any]]) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required; run this script through scripts/run-python"
        ) from exc

    width, height = card["canvas"]
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    for panel in panels:
        with Image.open(panel["source_path"]) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
            if panel.get("crop_box") is not None:
                x, y, crop_width, crop_height = parse_box(panel["crop_box"], "crop_box")
                if x + crop_width > source.width or y + crop_height > source.height:
                    raise ValueError(
                        f"crop_box exceeds source bounds: {panel['source_path']}"
                    )
                source = source.crop((x, y, x + crop_width, y + crop_height))
            x, y, box_width, box_height = parse_box(panel["target_box"], "target_box")
            if x + box_width > width or y + box_height > height:
                raise ValueError(
                    f"target_box exceeds card canvas: {card['id']} {panel['item_id']}"
                )
            rendered = ImageOps.contain(
                source, (box_width, box_height), method=Image.Resampling.LANCZOS
            )
            image_x = x + (box_width - rendered.width) // 2
            image_y = y + (box_height - rendered.height) // 2
            canvas.paste(rendered, (image_x, image_y))
            draw.rectangle(
                (x, y, x + box_width - 1, y + box_height - 1),
                outline="#d0d0d0",
                width=2,
            )
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def card_authority(panels: list[dict[str, Any]]) -> tuple[str, bool, list[str]]:
    authorities = sorted(
        {str(panel["source_authority"]) for panel in panels}, key=str.casefold
    )
    canonical_only = authorities == ["canonical-identity"]
    authority = (
        "official-derived-transport-bundle"
        if canonical_only
        else "user-directed-derived-identity-transport-bundle"
    )
    return authority, canonical_only, authorities


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def unmanaged_card_outputs(output_dir: Path, expected_files: set[str]) -> list[Path]:
    if not output_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in output_dir.iterdir()
            if path.is_file()
            and path.suffix.casefold() in CARD_IMAGE_EXTENSIONS
            and path.name not in expected_files
        ),
        key=lambda path: path.name.casefold(),
    )


def build_cards(
    recipes_path: Path,
    output_dir: Path,
    database: Path,
    *,
    check: bool,
) -> dict[str, Any]:
    recipes = load_recipes(recipes_path)
    recipe_sha256 = file_hash(recipes_path)
    connection = open_database(database, read_only=True)
    failures: list[str] = []
    cards: list[dict[str, Any]] = []
    try:
        for card in recipes["cards"]:
            panels = [
                resolve_panel(connection, panel, card) for panel in card["panels"]
            ]
            rendered = render_card(card, panels)
            output = output_dir / card["output_file"]
            rendered_sha256 = bytes_hash(rendered)
            if check:
                if not output.is_file():
                    failures.append(f"identity card is missing: {output}")
                elif file_hash(output) != rendered_sha256:
                    failures.append(f"identity card is stale: {output}")
            else:
                atomic_write_bytes(output, rendered)
            authority, canonical_only, source_authorities = card_authority(panels)
            cards.append(
                {
                    "id": card["id"],
                    "character": card["character"],
                    "form": card["form"],
                    "subject_kind": card.get("subject_kind", "character"),
                    "output_file": card["output_file"],
                    "output_sha256": rendered_sha256,
                    "dimensions": card["canvas"],
                    "authority": authority,
                    "canonical_sources_only": canonical_only,
                    "source_authorities": source_authorities,
                    "required_traits": card.get("required_traits", []),
                    "excluded_traits": card.get("excluded_traits", []),
                    "panels": [
                        {
                            key: (str(value) if key == "source_path" else value)
                            for key, value in panel.items()
                        }
                        for panel in panels
                    ],
                }
            )
    finally:
        connection.close()

    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schema_version": 1,
        "kind": recipes["output_kind"],
        "built_at": now_iso(),
        "recipe_path": str(recipes_path.resolve()),
        "recipe_sha256": recipe_sha256,
        "cards": cards,
    }
    if check:
        expected_files = {str(card["output_file"]) for card in cards}
        for stale in unmanaged_card_outputs(output_dir, expected_files):
            failures.append(f"unmanaged identity card output: {stale}")
        if not manifest_path.is_file():
            failures.append(f"identity card manifest is missing: {manifest_path}")
        else:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("recipe_sha256") != recipe_sha256:
                failures.append("identity card manifest recipe hash is stale")
            existing_cards = {
                card.get("id"): card for card in existing.get("cards", [])
            }
            for card in cards:
                existing_card = existing_cards.get(card["id"], {})
                if existing_card.get("output_sha256") != card["output_sha256"]:
                    failures.append(
                        f"identity card manifest output hash is stale: {card['id']}"
                    )
                for field in (
                    "authority",
                    "canonical_sources_only",
                    "source_authorities",
                    "subject_kind",
                ):
                    if existing_card.get(field) != card[field]:
                        failures.append(
                            f"identity card manifest {field} is stale: {card['id']}"
                        )
                existing_source_hashes = [
                    panel.get("source_sha256")
                    for panel in existing_card.get("panels", [])
                ]
                current_source_hashes = [
                    panel.get("source_sha256") for panel in card["panels"]
                ]
                if existing_source_hashes != current_source_hashes:
                    failures.append(
                        f"identity card manifest sources are stale: {card['id']}"
                    )
    else:
        atomic_write_json(manifest_path, manifest)
    return {
        "ok": not failures,
        "check": check,
        "recipes": str(recipes_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "manifest": str(manifest_path.resolve()),
        "card_count": len(cards),
        "cards": [
            {
                "id": card["id"],
                "form": card["form"],
                "output": str((output_dir / card["output_file"]).resolve()),
                "sha256": card["output_sha256"],
            }
            for card in cards
        ],
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else root / "identity-cards"
    )
    database = workflow_paths(root)["database"]
    if not database.is_file():
        raise SystemExit("Catalog missing; run build_reference_index.py first")
    result = build_cards(
        args.recipes.expanduser().resolve(),
        output_dir,
        database,
        check=args.check,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"identity_cards={result['card_count']} ok={str(result['ok']).lower()} "
            f"output={result['output_dir']}"
        )
        for failure in result["failures"]:
            print(f"FAIL: {failure}")
    return 2 if args.check and result["failures"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
