#!/usr/bin/env python3
"""Download page images from a publicly accessible NDL IIIF manifest, one volume at a time."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MANIFEST_TEMPLATE = "https://www.dl.ndl.go.jp/api/iiif/{pid}/manifest.json"
USER_AGENT = "bonsai-hokusai-manga/1.1 (NDL IIIF research downloader)"
IMAGE_SIGNATURES = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"GIF87a",
    b"GIF89a",
)


def fetch(url: str, timeout: int = 90, attempts: int = 4) -> tuple[bytes, str]:
    """Fetch a URL with backoff for transient failures; do not retry access-denied responses."""
    for attempt in range(attempts):
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": "https://www.dl.ndl.go.jp/",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except URLError:
            if attempt == attempts - 1:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not fetch {url}")


def label_text(label: object, fallback: str) -> str:
    if isinstance(label, str) and label:
        return label
    if isinstance(label, dict):
        for value in label.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str) and value:
                return value
    return fallback


def first_service(service: object) -> dict:
    if isinstance(service, list):
        service = service[0] if service else {}
    return service if isinstance(service, dict) else {}


def canvas_image(canvas: dict) -> tuple[str | None, str]:
    """Return an image URL/service ID and a useful canvas label (IIIF v2/v3)."""
    label = label_text(canvas.get("label"), "page")
    images = canvas.get("images", [])
    if images:
        resource = images[0].get("resource", {})
        service = first_service(resource.get("service"))
        service_id = service.get("@id") or service.get("id")
        if service_id:
            return str(service_id).rstrip("/"), label
        resource_id = resource.get("@id") or resource.get("id")
        if resource_id:
            return str(resource_id), label

    for annotation_page in canvas.get("items", []):
        for annotation in annotation_page.get("items", []):
            body = annotation.get("body", {})
            if isinstance(body, list):
                body = body[0] if body else {}
            if not isinstance(body, dict):
                continue
            service = first_service(body.get("service"))
            service_id = service.get("id") or service.get("@id")
            if service_id:
                return str(service_id).rstrip("/"), label
            body_id = body.get("id") or body.get("@id")
            if body_id:
                return str(body_id), label
    return None, label


def get_canvases(manifest: dict) -> list[dict]:
    sequences = manifest.get("sequences", [])
    if sequences:
        return sequences[0].get("canvases", [])
    return [item for item in manifest.get("items", []) if isinstance(item, dict)]


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value[:80] or "page"


def image_request_url(image_id: str) -> str:
    if "/full/" in image_id and image_id.lower().endswith((".jpg", ".jpeg", ".png", ".jp2")):
        return image_id
    return f"{image_id.rstrip('/')}/full/full/0/default.jpg"


def looks_like_image(data: bytes) -> bool:
    if any(data.startswith(signature) for signature in IMAGE_SIGNATURES):
        return True
    # WebP: RIFF....WEBP
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def update_dataset_metadata(
    metadata_path: Path, pid: str, manifest: dict, page_records: list[dict]
) -> None:
    if not metadata_path.exists():
        return
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARNING: cannot update {metadata_path}: {exc}")
        return
    volume = next(
        (item for item in metadata.get("volumes", []) if str(item.get("ndl_pid")) == pid),
        None,
    )
    if volume is None:
        print(f"WARNING: PID {pid} is not listed in {metadata_path}")
        return
    volume["manifest_label"] = label_text(manifest.get("label"), volume.get("volume_label", ""))
    volume["manifest_metadata"] = manifest.get("metadata", [])
    volume["page_count"] = len(page_records)
    volume["pages"] = page_records
    volume["metadata_updated_from_manifest"] = True
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def download(pid: str, output: Path, delay: float, metadata_path: Path) -> int:
    manifest_url = MANIFEST_TEMPLATE.format(pid=pid)
    folder = output / pid
    folder.mkdir(parents=True, exist_ok=True)
    try:
        raw, content_type = fetch(manifest_url)
        manifest = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        (folder / "errors.txt").write_text(
            f"manifest request failed: {exc}\n", encoding="utf-8"
        )
        raise
    (folder / "manifest.json").write_bytes(raw)
    (folder / "source.txt").write_text(
        f"NDL PID: {pid}\nManifest: {manifest_url}\n"
        "Check the NDL record's rights and access conditions before reuse.\n",
        encoding="utf-8",
    )

    canvases = get_canvases(manifest)
    if not canvases:
        raise RuntimeError(
            "No canvases found in the manifest. Inspect manifest.json; "
            f"response Content-Type was {content_type!r}."
        )

    pages = []
    for index, canvas in enumerate(canvases, start=1):
        image_id, label = canvas_image(canvas)
        filename = f"{index:04d}_{safe_filename(label)}.jpg"
        pages.append({
            "page_number": index,
            "label": label,
            "canvas_id": canvas.get("id") or canvas.get("@id"),
            "image_service_id": image_id,
            "image_url": image_request_url(image_id) if image_id else None,
            "local_file": f"output/{pid}/{filename}",
            "width": canvas.get("width"),
            "height": canvas.get("height"),
            "download_status": "pending" if image_id else "missing_image_id",
        })

    print(f"PID {pid}: found {len(canvases)} canvases")
    saved = 0
    errors: list[str] = []
    for index, page in enumerate(pages, start=1):
        image_id = page["image_service_id"]
        url = page["image_url"]
        filename = Path(page["local_file"]).name
        destination = folder / filename
        if not image_id:
            errors.append(f"page {index}: no image service or resource ID")
            continue
        if destination.exists() and destination.stat().st_size > 0:
            existing = destination.read_bytes()
            if looks_like_image(existing):
                print(f"[{index}/{len(canvases)}] exists: {filename}")
                page["download_status"] = "available"
                page["local_bytes"] = len(existing)
                saved += 1
                continue
            destination.unlink()
        try:
            image_bytes, image_type = fetch(url, timeout=120)
            if not looks_like_image(image_bytes):
                raise RuntimeError(
                    f"response is not a recognized image (Content-Type={image_type!r}, "
                    f"bytes={len(image_bytes)})"
                )
            destination.write_bytes(image_bytes)
            page["download_status"] = "downloaded"
            page["local_bytes"] = len(image_bytes)
            page["content_type"] = image_type
            saved += 1
            print(f"[{index}/{len(canvases)}] saved {filename} ({len(image_bytes):,} bytes; {image_type or 'unknown type'})")
        except Exception as exc:
            page["download_status"] = "error"
            page["error"] = str(exc)
            errors.append(f"page {index} ({url}): {exc}")
            print(f"[{index}/{len(canvases)}] ERROR: {exc}")
        time.sleep(delay)

    update_dataset_metadata(metadata_path, pid, manifest, pages)
    (folder / "pages.json").write_text(
        json.dumps({"pid": pid, "manifest_url": manifest_url, "page_count": len(pages), "pages": pages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if errors:
        (folder / "errors.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")
        print(f"Completed with {len(errors)} page errors; see {folder / 'errors.txt'}")
    else:
        (folder / "errors.txt").unlink(missing_ok=True)
    print(f"Saved/available: {saved}/{len(canvases)} pages in {folder}")
    return 2 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, help="NDL digital collection PID, e.g. 851659")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--delay", type=float, default=1.5, help="seconds between image requests")
    parser.add_argument("--metadata", type=Path, default=Path("metadata.json"), help="dataset metadata JSON to update")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.pid):
        parser.error("PID may contain only letters, digits, underscores, and hyphens")
    if args.delay < 0.5:
        parser.error("--delay must be at least 0.5 seconds to pace requests")
    return download(args.pid, args.output, args.delay, args.metadata)


if __name__ == "__main__":
    raise SystemExit(main())
