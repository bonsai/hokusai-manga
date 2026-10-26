#!/usr/bin/env python3
"""Download page images from a publicly accessible NDL IIIF manifest."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MANIFEST_TEMPLATE = "https://www.dl.ndl.go.jp/api/iiif/{pid}/manifest.json"
USER_AGENT = "bonsai-hokusai-manga/1.0 (NDL IIIF research downloader)"


def fetch(url: str, timeout: int = 90, attempts: int = 4) -> tuple[bytes, str]:
    """Fetch a URL with a small backoff for transient failures."""
    for attempt in range(attempts):
        request = Request(url, headers={"User-Agent": USER_AGENT})
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

    # Presentation API 2: canvas.images[].resource.service
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

    # Presentation API 3: canvas.items[].items[].body.service
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
    # IIIF Presentation API 2
    sequences = manifest.get("sequences", [])
    if sequences:
        return sequences[0].get("canvases", [])
    # IIIF Presentation API 3
    for item in manifest.get("items", []):
        if isinstance(item, dict) and item.get("type") == "Canvas":
            pass
    return [item for item in manifest.get("items", []) if isinstance(item, dict)]


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value[:80] or "page"


def image_request_url(image_id: str) -> str:
    # IIIF Image API request for the full image. The provider may impose a
    # maximum output size; "full" does not guarantee the archival master.
    if "/full/" in image_id and image_id.lower().endswith((".jpg", ".jpeg", ".png", ".jp2")):
        return image_id
    return f"{image_id.rstrip('/')}/full/full/0/default.jpg"


def download(pid: str, output: Path, delay: float) -> int:
    manifest_url = MANIFEST_TEMPLATE.format(pid=pid)
    raw, content_type = fetch(manifest_url)
    manifest = json.loads(raw.decode("utf-8-sig"))
    folder = output / pid
    folder.mkdir(parents=True, exist_ok=True)
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

    print(f"PID {pid}: found {len(canvases)} canvases")
    saved = 0
    errors: list[str] = []
    for index, canvas in enumerate(canvases, start=1):
        image_id, label = canvas_image(canvas)
        if not image_id:
            errors.append(f"page {index}: no image service or resource ID")
            continue

        url = image_request_url(image_id)
        filename = f"{index:04d}_{safe_filename(label)}.jpg"
        destination = folder / filename
        if destination.exists() and destination.stat().st_size > 0:
            print(f"[{index}/{len(canvases)}] exists: {filename}")
            saved += 1
            continue

        try:
            image_bytes, image_type = fetch(url, timeout=120)
            if not image_type.lower().startswith("image/"):
                raise RuntimeError(f"expected image response, got {image_type!r}")
            destination.write_bytes(image_bytes)
            saved += 1
            print(f"[{index}/{len(canvases)}] saved {filename} ({len(image_bytes):,} bytes)")
        except Exception as exc:  # keep a log and continue other pages
            errors.append(f"page {index} ({url}): {exc}")
            print(f"[{index}/{len(canvases)}] ERROR: {exc}")
        time.sleep(delay)

    if errors:
        (folder / "errors.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")
        print(f"Completed with {len(errors)} page errors; see {folder / 'errors.txt'}")
    print(f"Saved/available: {saved}/{len(canvases)} pages in {folder}")
    return 0 if not errors else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, help="NDL digital collection PID, e.g. 851659")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between image requests")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.pid):
        parser.error("PID may contain only letters, digits, underscores, and hyphens")
    if args.delay < 0.25:
        parser.error("--delay must be at least 0.25 seconds to pace requests")
    return download(args.pid, args.output, args.delay)


if __name__ == "__main__":
    raise SystemExit(main())
