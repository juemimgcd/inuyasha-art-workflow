#!/usr/bin/env python3
"""Composite a generated local-edit crop into its original target image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from task_workflow import read_json
from workflow_common import atomic_write_json


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inner_feather_mask(size: tuple[int, int], feather: int):
    from PIL import Image, ImageDraw

    width, height = size
    mask = Image.new("L", size, 255)
    feather = min(max(feather, 0), width // 2, height // 2)
    if feather == 0:
        return mask
    draw = ImageDraw.Draw(mask)
    for inset in range(feather):
        value = round(255 * inset / feather)
        draw.rectangle(
            (inset, inset, width - 1 - inset, height - 1 - inset),
            outline=value,
        )
    return mask


def outside_edit_box_equal(
    source_path: Path,
    output_path: Path,
    edit_box: tuple[int, int, int, int],
) -> bool:
    from PIL import Image, ImageChops, ImageDraw

    with (
        Image.open(source_path) as source_image,
        Image.open(output_path) as output_image,
    ):
        source = source_image.convert("RGBA")
        output = output_image.convert("RGBA")
        if source.size != output.size:
            return False
        difference = ImageChops.difference(source, output)
        x, y, width, height = edit_box
        ImageDraw.Draw(difference).rectangle(
            (x, y, x + width - 1, y + height - 1), fill=(0, 0, 0, 0)
        )
        return difference.getbbox() is None


def composite_local_edit(
    target: Path,
    candidate: Path,
    output: Path,
    context_box: tuple[int, int, int, int],
    edit_box: tuple[int, int, int, int],
    feather: int,
) -> dict[str, object]:
    from PIL import Image

    context_x, context_y, context_width, context_height = context_box
    edit_x, edit_y, edit_width, edit_height = edit_box
    relative_box = (
        edit_x - context_x,
        edit_y - context_y,
        edit_x - context_x + edit_width,
        edit_y - context_y + edit_height,
    )
    if min(relative_box[0], relative_box[1]) < 0:
        raise ValueError("edit box starts outside the context box")
    if relative_box[2] > context_width or relative_box[3] > context_height:
        raise ValueError("edit box ends outside the context box")

    with Image.open(target) as target_image, Image.open(candidate) as candidate_image:
        source = target_image.convert("RGBA")
        generated = candidate_image.convert("RGBA")
        resized = generated.size != (context_width, context_height)
        if resized:
            generated = generated.resize(
                (context_width, context_height), Image.Resampling.LANCZOS
            )
        replacement = generated.crop(relative_box)
        mask = inner_feather_mask((edit_width, edit_height), feather)
        result = source.copy()
        result.paste(replacement, (edit_x, edit_y), mask)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.save(output, format="PNG")

    return {
        "target": str(target),
        "candidate": str(candidate),
        "output": str(output),
        "target_sha256": file_hash(target),
        "candidate_sha256": file_hash(candidate),
        "output_sha256": file_hash(output),
        "context_box": list(context_box),
        "edit_box": list(edit_box),
        "feather_pixels": feather,
        "candidate_resized_to_context": resized,
        "outside_edit_box_preserved": outside_edit_box_equal(target, output, edit_box),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--feather-pixels", type=int)
    args = parser.parse_args()

    task_dir = args.task_dir.expanduser().resolve()
    brief = read_json(task_dir / "brief.json")
    local_edit = brief.get("local_edit") or {}
    if local_edit.get("mode") != "crop-composite":
        raise SystemExit("task is not configured for crop-composite local editing")
    target = Path(local_edit["target"]).expanduser().resolve()
    candidate = args.candidate.expanduser().resolve()
    if not target.is_file():
        raise SystemExit(f"target image is missing: {target}")
    if not candidate.is_file():
        raise SystemExit(f"candidate image is missing: {candidate}")
    output = (
        args.output.expanduser().resolve()
        if args.output
        else task_dir / "outputs" / f"{candidate.stem}-composited.png"
    )
    feather = (
        args.feather_pixels
        if args.feather_pixels is not None
        else int(local_edit.get("feather_pixels", 8))
    )
    if feather < 0:
        raise SystemExit("--feather-pixels must be zero or greater")

    report = composite_local_edit(
        target,
        candidate,
        output,
        tuple(local_edit["context_box"]),
        tuple(local_edit["edit_box"]),
        feather,
    )
    report_path = output.with_suffix(".local-edit.json")
    atomic_write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
