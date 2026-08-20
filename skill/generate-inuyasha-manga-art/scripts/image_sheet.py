#!/usr/bin/env python3
"""Pillow helpers for reference browsing and candidate-versus-style QA."""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from collections.abc import Sequence
from pathlib import Path

from workflow_common import atomic_write_json, resolve_recorded_path

FONT_CANDIDATES = (
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
)


def load_font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_contact_sheet(
    entries: Sequence[tuple[Path, str]],
    output: Path,
    *,
    columns: int = 3,
    thumb_size: tuple[int, int] = (420, 560),
    background: str = "#f4f1ea",
) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required; run this script through scripts/run-python"
        ) from exc
    if not entries:
        raise ValueError("Cannot build a contact sheet without images")
    if columns < 1:
        raise ValueError("columns must be positive")

    label_height = 78
    gap = 18
    margin = 24
    cell_width = thumb_size[0]
    cell_height = thumb_size[1] + label_height
    rows = (len(entries) + columns - 1) // columns
    canvas_width = margin * 2 + columns * cell_width + (columns - 1) * gap
    canvas_height = margin * 2 + rows * cell_height + (rows - 1) * gap
    canvas = Image.new("RGB", (canvas_width, canvas_height), background)
    draw = ImageDraw.Draw(canvas)
    font = load_font(17)

    for index, (path, label) in enumerate(entries):
        row, column = divmod(index, columns)
        x = margin + column * (cell_width + gap)
        y = margin + row * (cell_height + gap)
        with Image.open(path) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            thumbnail = ImageOps.contain(source, thumb_size)
        image_x = x + (cell_width - thumbnail.width) // 2
        image_y = y + (thumb_size[1] - thumbnail.height) // 2
        canvas.paste(thumbnail, (image_x, image_y))
        draw.rectangle(
            [x, y, x + cell_width - 1, y + thumb_size[1] - 1],
            outline="#a49d90",
            width=2,
        )
        visible_label = "\n".join(
            textwrap.wrap(
                label,
                width=24,
                max_lines=2,
                placeholder="...",
                break_long_words=True,
                break_on_hyphens=False,
            )
        )
        draw.multiline_text(
            (x + 4, y + thumb_size[1] + 10), visible_label, fill="#171717", font=font
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    canvas.save(temporary, format="JPEG", quality=90, optimize=True)
    temporary.replace(output)
    return output


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepared_reference_path(task_dir: Path, entry: dict) -> Path:
    value = entry.get("rendered_path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"style reference has no rendered_path: {entry.get('item_id')}")
    path = resolve_recorded_path(value)
    if not path.is_file():
        fallback = task_dir / "references" / Path(value).name
        if fallback.is_file():
            path = fallback.resolve()
    if not path.is_file():
        raise ValueError(f"prepared style reference is missing: {path}")
    expected_hash = entry.get("rendered_content_hash") or entry.get("content_hash")
    if not isinstance(expected_hash, str) or file_hash(path) != expected_hash:
        raise ValueError(f"prepared style reference hash mismatch: {path}")
    return path


def build_style_comparison_sheet(
    task_dir: Path,
    candidate: Path,
    output: Path | None = None,
) -> tuple[Path, Path]:
    """Build a labeled row per selected style scope and a hash-locked sidecar."""
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required; run this script through scripts/run-python"
        ) from exc
    task_dir = task_dir.expanduser().resolve()
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise ValueError(f"candidate image is missing: {candidate}")
    manifest_path = task_dir / "reference-manifest.json"
    brief_path = task_dir / "brief.json"
    if not manifest_path.is_file() or not brief_path.is_file():
        raise ValueError("--task-dir must contain brief.json and reference-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    style_entries = [
        entry
        for entry in manifest.get("references", [])
        if isinstance(entry, dict) and entry.get("role") == "style"
    ]
    if not style_entries:
        raise ValueError("the task has no selected style reference to compare")
    prepared = [
        (entry, _prepared_reference_path(task_dir, entry)) for entry in style_entries
    ]
    output = (
        output.expanduser().resolve()
        if output is not None
        else task_dir
        / "qa-comparisons"
        / f"{candidate.stem}-manga-style-comparison.png"
    )
    if output.suffix.casefold() != ".png":
        raise ValueError("style comparison output must use a .png suffix")

    thumb_size = (560, 640)
    label_height = 118
    title_height = 92
    gap = 22
    margin = 28
    cell_width = thumb_size[0]
    cell_height = thumb_size[1] + label_height
    rows = len(prepared)
    canvas_width = margin * 2 + cell_width * 2 + gap
    canvas_height = margin * 2 + title_height + rows * cell_height + (rows - 1) * gap
    canvas = Image.new("RGB", (canvas_width, canvas_height), "#f4f1ea")
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(24)
    label_font = load_font(17)
    draw.text(
        (margin, margin),
        "Manga style QA — candidate beside each selected style authority",
        fill="#171717",
        font=title_font,
    )
    draw.text(
        (margin, margin + 38),
        "Compare only the declared character/scene scope; identity and content remain separate.",
        fill="#4a463f",
        font=label_font,
    )

    def draw_cell(path: Path, label: str, row: int, column: int) -> tuple[int, int]:
        x = margin + column * (cell_width + gap)
        y = margin + title_height + row * (cell_height + gap)
        with Image.open(path) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            dimensions = source.size
            thumbnail = ImageOps.contain(source, thumb_size)
        image_x = x + (cell_width - thumbnail.width) // 2
        image_y = y + (thumb_size[1] - thumbnail.height) // 2
        canvas.paste(thumbnail, (image_x, image_y))
        draw.rectangle(
            [x, y, x + cell_width - 1, y + thumb_size[1] - 1],
            outline="#8d867a",
            width=2,
        )
        visible_label = "\n".join(
            textwrap.wrap(
                label,
                width=54,
                max_lines=4,
                placeholder="...",
                break_long_words=True,
                break_on_hyphens=False,
            )
        )
        draw.multiline_text(
            (x + 4, y + thumb_size[1] + 10),
            visible_label,
            fill="#171717",
            font=label_font,
            spacing=4,
        )
        return dimensions

    candidate_dimensions = (0, 0)
    rows_metadata = []
    rendering_map = brief.get("rendering_map") or {}
    for row, (entry, style_path) in enumerate(prepared):
        scope = entry.get("style_scope") or "legacy"
        scope_map = rendering_map.get("character" if scope == "character" else "scene") or {}
        compare_focus = (
            scope_map.get("resolve")
            if scope == "character"
            else scope_map.get("focal_plane")
        ) or "declared style focus"
        candidate_dimensions = draw_cell(
            candidate,
            f"Candidate | compare {scope} rendering | {compare_focus}",
            row,
            0,
        )
        style_dimensions = draw_cell(
            style_path,
            f"Input {entry.get('order', '?')} | {scope} style | {entry.get('focus') or 'declared focus'}",
            row,
            1,
        )
        rows_metadata.append(
            {
                "order": entry.get("order"),
                "item_id": entry.get("item_id"),
                "style_scope": scope,
                "focus": entry.get("focus") or "",
                "path": str(style_path),
                "sha256": file_hash(style_path),
                "dimensions": list(style_dimensions),
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    canvas.save(temporary, format="PNG", optimize=True)
    temporary.replace(output)
    sidecar = output.with_suffix(".json")
    metadata = {
        "schema_version": 1,
        "kind": "manga-style-comparison",
        "task_id": brief.get("task_id") or task_dir.name,
        "candidate": {
            "path": str(candidate),
            "sha256": file_hash(candidate),
            "dimensions": list(candidate_dimensions),
        },
        "style_rows": rows_metadata,
        "rendering_map_schema_version": rendering_map.get("schema_version"),
        "sheet": {"path": str(output), "sha256": file_hash(output)},
    }
    atomic_write_json(sidecar, metadata)
    return output, sidecar


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sheet, sidecar = build_style_comparison_sheet(
        args.task_dir, args.candidate, args.output
    )
    print(
        json.dumps(
            {"comparison_sheet": str(sheet), "comparison_sidecar": str(sidecar)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
