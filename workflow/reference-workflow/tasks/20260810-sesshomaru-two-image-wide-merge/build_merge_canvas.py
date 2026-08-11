from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


LEFT = Path(
    "/Users/jquery/Library/Containers/com.tencent.qq/Data/tmp/"
    "34e826ad-e49f-446d-9641-4922f56b4fd8.png"
)
RIGHT = Path(
    "/Users/jquery/Library/Containers/com.tencent.qq/Data/tmp/"
    "bf6f2c49-752f-4a4c-866f-613ed2b47c93.png"
)
OUTPUTS = Path(__file__).resolve().parent / "outputs"


def normalized_manga(path: Path) -> Image.Image:
    image = Image.open(path).convert("L")
    image = ImageOps.autocontrast(image, cutoff=(0.15, 0.15))
    return ImageEnhance.Contrast(image).enhance(1.02)


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    left = normalized_manga(LEFT)
    right = normalized_manga(RIGHT)

    # The QQ-exported first image contains a 28 px light-gray preview gutter on
    # its right edge. It is UI chrome rather than artwork, so remove it before
    # scaling and joining the two illustrations.
    left = left.crop((0, 0, 450, left.height))

    target_height = right.height
    left_width = round(left.width * target_height / left.height)
    left = left.resize((left_width, target_height), Image.Resampling.LANCZOS)

    canvas = Image.new("L", (left.width + right.width, target_height), 255)
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width, 0))
    canvas.save(OUTPUTS / "sesshomaru-merge-base.png", optimize=True)

    # The seam crop uses a 2:3 aspect ratio so an edited result can be scaled
    # back without geometric distortion. Character faces remain outside it.
    crop_width = 968
    crop_left = left.width - crop_width // 2
    crop = canvas.crop((crop_left, 0, crop_left + crop_width, target_height))
    crop.save(OUTPUTS / "sesshomaru-seam-context.png", optimize=True)

    metadata = (
        f"canvas={canvas.width}x{canvas.height}\n"
        f"seam_x={left.width}\n"
        f"context_crop={crop_left},0,{crop_width},{target_height}\n"
    )
    (OUTPUTS / "merge-layout.txt").write_text(metadata, encoding="utf-8")


if __name__ == "__main__":
    main()
