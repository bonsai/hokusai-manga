#!/usr/bin/env python3
"""
Hokusai VLM dashboard server — FastAPI + plotly.py.

Run:
    python agents/skills/viewer/server.py          # http://127.0.0.1:3002
    PORT=8080 python agents/skills/viewer/server.py

Pages:
    /            dashboard (plotly.py figures, grid/list/tags/detail/TTS/sequence)
    /viewer      volume metadata viewer (docs/viewer.html)
    /healthz     health check

API:
    /api/get?ids=LATEST        latest review(s); also accepts image names or indexes
    /api/reviews?tag=&category=&min_suit=&q=&limit=&offset=
    /api/stats                 aggregates used by the dashboard
    /api/metadata              docs/data/metadata.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# Import the shared renderer/data loaders from the sibling worker
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_report import build_dashboard, collect_meta, compute_stats, load_all_images  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = REPO_ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
IMAGES_DIR = DOCS_DIR / "images"
IMG_INDEX_DIR = DOCS_DIR / "img"
JSONL_PATH = DATA_DIR / "hokusai_vlm_reviews.jsonl"
DB_PATH = DATA_DIR / "hokusai_vlm_reviews.db"
METADATA_PATH = DATA_DIR / "metadata.json"

app = FastAPI(title="Hokusai VLM Dashboard", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

for _mount, _dir in (("/images", IMAGES_DIR), ("/img", IMG_INDEX_DIR), ("/data", DATA_DIR)):
    if _dir.exists():
        app.mount(_mount, StaticFiles(directory=str(_dir)), name=_mount.strip("/"))


_CACHE: dict = {"key": None, "data": None, "html": None}


def _data_key() -> tuple:
    key = []
    for path in (JSONL_PATH, DB_PATH):
        try:
            key.append(path.stat().st_mtime_ns)
        except OSError:
            key.append(0)
    return tuple(key)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_data(force: bool = False) -> dict:
    """Load reviews/aggregates, rebuilding only when the data files change."""
    key = _data_key()
    if force or _CACHE["data"] is None or _CACHE["key"] != key:
        all_images, errors = load_all_images(JSONL_PATH, DB_PATH)
        stats = compute_stats([i for i in all_images if not i.get("_error")])
        tag_counts, vol_counts, detail = collect_meta(all_images)
        _CACHE.update(
            key=key,
            html=None,
            data={
                "all_images": all_images,
                "errors": errors,
                "items": detail,
                "stats": stats,
                "tags": dict(tag_counts),
                "volumes": {f"Vol {v}": c for v, c in sorted(vol_counts.items())},
            },
        )
    return _CACHE["data"]


def get_html() -> str:
    data = get_data()
    if _CACHE["html"] is None:
        _CACHE["html"] = build_dashboard(
            data["all_images"],
            data["errors"],
            img_dir="/images",
            output=None,
            title="Hokusai VLM Dashboard",
            plotly_js="/static/plotly.min.js",
        )
    return _CACHE["html"]


@lru_cache(maxsize=1)
def _plotly_js() -> str:
    # plotly.py bundles plotly.js locally, so no CDN / unpkg request is made.
    from plotly.offline import get_plotlyjs

    return get_plotlyjs()


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(get_html())


@app.get("/viewer", response_class=HTMLResponse)
@app.get("/volumes", response_class=HTMLResponse)
def volume_viewer() -> HTMLResponse:
    return HTMLResponse((DOCS_DIR / "viewer.html").read_text(encoding="utf-8"))


@app.get("/static/plotly.min.js")
def plotly_js() -> Response:
    return Response(
        _plotly_js(),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/api/health")
@app.get("/healthz")
def health() -> dict:
    data = get_data()
    return {
        "status": "ok",
        "reviews": len(data["items"]),
        "errors": len(data["errors"]),
        "updated_at": _iso_now(),
    }


@app.get("/api/stats")
def api_stats() -> JSONResponse:
    data = get_data()
    stats = data["stats"]
    return JSONResponse({
        "total": stats["total"],
        "avg_suitability": stats["avg_suitability"],
        "median_suitability": stats["median_suitability"],
        "categories": dict(stats["categories"]),
        "quality": stats["quality"],
        "suitability": {str(k): v for k, v in stats["suit_dist"].items()},
        "tags": data["tags"],
        "volumes": data["volumes"],
        "errors": len(data["errors"]),
        "updated_at": _iso_now(),
    })


@app.get("/api/metadata")
def api_metadata() -> JSONResponse:
    if not METADATA_PATH.exists():
        return JSONResponse({"error": "metadata.json not found"}, status_code=404)
    return JSONResponse(json.loads(METADATA_PATH.read_text(encoding="utf-8")))


def _filter_items(
    items: list[dict],
    tag: str | None,
    category: str | None,
    min_suit: int | None,
    q: str | None,
) -> list[dict]:
    out = items
    if tag:
        out = [d for d in out if tag in d.get("tags", [])]
    if category:
        out = [d for d in out if d.get("category") == category or category in d.get("tags", [])]
    if min_suit is not None:
        out = [d for d in out if d.get("suit", 0) >= min_suit]
    if q:
        needle = q.lower()
        out = [
            d for d in out
            if needle in d.get("image", "").lower()
            or needle in d.get("subject", "").lower()
            or needle in d.get("notes", "").lower()
        ]
    return out


@app.get("/api/reviews")
def api_reviews(
    tag: str | None = None,
    category: str | None = None,
    min_suit: int | None = Query(default=None, ge=0, le=10),
    q: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    data = get_data()
    items = _filter_items(data["items"], tag, category, min_suit, q)
    total = len(items)
    page = items[offset: offset + limit]
    return JSONResponse({
        "count": len(page),
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": page,
        "updated_at": _iso_now(),
    })


@app.get("/api/get")
def api_get(
    ids: str = Query(default="LATEST", description="LATEST, comma-separated image names, or indexes"),
    limit: int = Query(default=20, ge=1, le=500),
) -> JSONResponse:
    """Generic fetch-by-id endpoint (also answers preview harnesses polling LATEST)."""
    data = get_data()
    items = data["items"]
    wanted = [s.strip() for s in ids.replace(";", ",").split(",") if s.strip()]
    picked: list[dict] = []

    if not wanted or any(w.upper() in {"LATEST", "*", "ALL"} for w in wanted):
        picked = items[-limit:][::-1]
    else:
        by_name = {d["image"]: d for d in items}
        by_stem = {Path(d["image"]).stem: d for d in items}
        for w in wanted:
            if w in by_name:
                picked.append(by_name[w])
            elif w in by_stem:
                picked.append(by_stem[w])
            elif w.isdigit() and 0 <= int(w) < len(items):
                picked.append(items[int(w)])
    # Some preview harnesses expect a `clips` array and call .find() on it.
    clips = [
        {
            **d,
            "id": d["image"],
            "clip_id": d["image"],
            "name": d["image"],
            "title": d.get("subject") or d["image"],
            "content": d.get("notes") or "",
            "type": "image",
            "url": f"/images/{d['image']}",
        }
        for d in picked
    ]
    return JSONResponse({
        "ids": wanted,
        "count": len(picked),
        "items": picked,
        "clips": clips,
        "updated_at": _iso_now(),
    })


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "3002")),
        reload=False,
    )
