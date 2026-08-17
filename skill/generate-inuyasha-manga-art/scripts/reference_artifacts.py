"""File, image, and identity-card artifacts used by reference workflows."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from workflow_common import (
    find_executable,
    open_database,
    resolve_recorded_path,
    workflow_paths,
)

IDENTITY_CARD_RECIPES = (
    Path(__file__).resolve().parent.parent / "references" / "identity-card-recipes.json"
)


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            image.crop((x, y, x + width, y + height)).save(target, format="PNG")
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
        raise ValueError("identity card recipes changed; run build_identity_cards.py first")
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
    connection = open_database(workflow_paths(root)["database"], read_only=True)
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
    checks = {
        "content_hash": (card.get("output_sha256"), "manifest hash"),
        "card_id": (card.get("id"), "id"),
        "source_authority": (card.get("authority"), "authority"),
        "source_item_ids": (
            list(dict.fromkeys(panel["item_id"] for panel in card["panels"])),
            "source ids",
        ),
        "source_hashes": (
            list(dict.fromkeys(panel["source_sha256"] for panel in card["panels"])),
            "source hashes",
        ),
    }
    for field, (expected, label) in checks.items():
        if entry.get(field) != expected:
            raise ValueError(f"identity card {label} mismatch: {expected_item_id}")
    rendered = resolve_recorded_path(entry.get("rendered_path", ""))
    if rendered != output.resolve() or file_hash(rendered) != card.get("output_sha256"):
        raise ValueError(f"identity card rendered path is stale: {expected_item_id}")
    return expected_item_id, character
