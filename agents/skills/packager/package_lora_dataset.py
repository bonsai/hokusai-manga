#!/usr/bin/env python3
"""Prepare NDL Hokusai Manga pages as a compact, captioned LoRA ZIP."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
CAPTION = (
    "hokusai_manga, Japanese ukiyo-e manga illustration, "
    "Katsushika Hokusai, traditional Japanese drawing"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("output"))
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--max-side", type=int, default=1024)
    parser.add_argument("--quality", type=int, default=88)
    args = parser.parse_args()

    if args.max_side < 256:
        parser.error("--max-side must be at least 256")
    if not 60 <= args.quality <= 95:
        parser.error("--quality must be between 60 and 95")

    args.output.mkdir(parents=True, exist_ok=True)
    staging = args.output / "hokusai_manga_lora"
    images_dir = staging / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    source_images = sorted(
        p for p in args.input.glob("*/*")
        if p.is_file() and p.suffix.lower() in SUPPORTED
        and p.name.lower() not in {"manifest.json"}
    )
    if not source_images:
        raise SystemExit(f"No page images found under {args.input}/*/")

    records = []
    total_before = 0
    total_after = 0
    for index, path in enumerate(source_images, start=1):
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            original_size = image.size
            image.thumbnail((args.max_side, args.max_side), Image.Resampling.LANCZOS)
            out_name = f"{path.parent.name}_{path.stem}.jpg"
            target = images_dir / out_name
            image.save(target, format="JPEG", quality=args.quality, optimize=True, progressive=True)
        before = path.stat().st_size
        after = target.stat().st_size
        total_before += before
        total_after += after
        (images_dir / f"{target.stem}.txt").write_text(CAPTION + "\n", encoding="utf-8")
        records.append({
            "file": f"images/{out_name}",
            "source": str(path),
            "source_bytes": before,
            "output_bytes": after,
            "source_size": list(original_size),
            "output_size": list(image.size),
            "caption": CAPTION,
        })
        if index % 100 == 0:
            print(f"Prepared {index}/{len(source_images)} images")

    manifest = {
        "title": "Hokusai Manga - NDL public-domain digital images",
        "trigger": "hokusai_manga",
        "caption": CAPTION,
        "image_count": len(records),
        "max_side": args.max_side,
        "jpeg_quality": args.quality,
        "source_bytes": total_before,
        "prepared_image_bytes": total_after,
        "images": records,
        "note": "Verify each NDL record's rights/access conditions before reuse.",
    }
    (staging / "dataset.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (staging / "README.txt").write_text(
        "Hokusai Manga LoRA dataset\n"
        f"Images: {len(records)}\n"
        f"Trigger: hokusai_manga\n"
        f"Resize: longest side <= {args.max_side}px\n"
        f"JPEG quality: {args.quality}\n"
        "Each image has a same-name .txt caption. See dataset.json for provenance.\n"
        "Source records: National Diet Library Digital Collections; verify rights per record.\n",
        encoding="utf-8",
    )

    zip_path = args.output / "hokusai_manga_lora_dataset.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(staging.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(args.output))

    print(f"Images: {len(records)}")
    print(f"Source image bytes: {total_before:,}")
    print(f"Prepared image bytes: {total_after:,}")
    print(f"ZIP: {zip_path} ({zip_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
