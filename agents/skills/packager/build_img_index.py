#!/usr/bin/env python3
"""Build img/index.json so viewer.html can display local image files."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = ROOT / "docs"
IMG_DIR = DOCS_DIR / "images"
INDEX_PATH = DOCS_DIR / "img" / "index.json"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def infer_volume(path: Path) -> tuple[int | None, str | None]:
    text = str(path.relative_to(IMG_DIR)).replace("\\", "/")
    pid_match = re.search(r"(?<!\d)(8516(?:4[6-9]|5[0-9]|60))(?!\d)", text)
    if pid_match:
        pid = int(pid_match.group(1))
        return pid - 851645, str(pid)
    patterns = [
        r"(?i)(?:volume|vol|v)[ _.-]*(0?\d{1,2})(?!\d)",
        r"第\s*(\d{1,2})\s*(?:編|篇|巻|卷)",
    ]
    for pattern in patterns:
        match = re.search(pattern, path.stem)
        if match:
            volume = int(match.group(1))
            if 1 <= volume <= 15:
                return volume, None
    return None, None


def main() -> None:
    if not IMG_DIR.exists():
        raise SystemExit(f"Image directory not found: {IMG_DIR}")
    images = []
    for path in sorted(IMG_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        relative = path.relative_to(DOCS_DIR).as_posix()
        volume, pid = infer_volume(path)
        images.append({
            "filename": path.name,
            "url": relative,
            "relative_path": relative,
            "volume": volume,
            "ndl_pid": pid,
            "bytes": path.stat().st_size,
        })
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps({"images": images, "image_count": len(images)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {INDEX_PATH.relative_to(ROOT)} with {len(images)} image(s).")
    unassigned = sum(1 for image in images if image["volume"] is None)
    if unassigned:
        print(f"{unassigned} image(s) could not be mapped to a volume by filename.")
        print("Rename them to include a PID (851646-851660) or volume label (vol01, volume-1, 第1編).")


if __name__ == "__main__":
    main()
