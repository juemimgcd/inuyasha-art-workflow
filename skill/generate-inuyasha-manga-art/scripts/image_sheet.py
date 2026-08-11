#!/usr/bin/env python3
"""Small Pillow helpers shared by browse and reference-set scripts."""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from pathlib import Path

FONT_CANDIDATES = (
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
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
