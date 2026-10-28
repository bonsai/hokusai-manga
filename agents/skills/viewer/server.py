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
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import the shared renderer/data loaders from the sibling worker
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_report import build_dashboard, collect_meta, compute_stats, load_all_images  # noqa: E402
from vlm_demo import DEFAULT_PROMPT as VLM_DEFAULT_PROMPT, PAGE_HTML as VLM_PAGE_HTML  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = REPO_ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
IMAGES_DIR = DOCS_DIR / "images"
IMG_INDEX_DIR = DOCS_DIR / "img"
JSONL_PATH = DATA_DIR / "hokusai_vlm_reviews.jsonl"
DB_PATH = DATA_DIR / "hokusai_vlm_reviews.db"
METADATA_PATH = DATA_DIR / "metadata.json"

VLM_BASE_URL = os.environ.get("VLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
VLM_MODEL = os.environ.get("VLM_MODEL", "tempura-qwen2.5-vl-3b")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "")

app = FastAPI(title="Hokusai VLM Dashboard", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
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
            vlm_demo_url="/vlm",
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


class VLMRequest(BaseModel):
    image: str
    prompt: str | None = None
    model: str | None = None
    max_tokens: int = 1000


def _vlm_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if VLM_API_KEY:
        headers["Authorization"] = f"Bearer {VLM_API_KEY}"
    return headers


def _normalize_image(image: str) -> str:
    image = (image or "").strip()
    if image.startswith("data:image/"):
        return image
    if len(image) > 100:
        return "data:image/jpeg;base64," + image
    raise HTTPException(status_code=400, detail="image must be a data URL or base64 string")


@app.get("/vlm", response_class=HTMLResponse)
@app.get("/vlm/", response_class=HTMLResponse)
def vlm_demo() -> HTMLResponse:
    return HTMLResponse(VLM_PAGE_HTML)


@app.get("/api/vlm/health")
def api_vlm_health() -> JSONResponse:
    try:
        req = urlrequest.Request(VLM_BASE_URL + "/models", headers=_vlm_headers(), method="GET")
        with urlrequest.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict) and m.get("id")]
        effective_model = VLM_MODEL if VLM_MODEL in models else (models[0] if models else VLM_MODEL)
        return JSONResponse({
            "server": True,
            "vlm": True,
            "base_url": VLM_BASE_URL,
            "model": effective_model,
            "models": models,
            "updated_at": _iso_now(),
        })
    except Exception as exc:
        return JSONResponse({
            "server": True,
            "vlm": False,
            "base_url": VLM_BASE_URL,
            "model": VLM_MODEL,
            "models": [],
            "error": f"{type(exc).__name__}: {exc}",
            "updated_at": _iso_now(),
        })


@app.post("/api/vlm")
def api_vlm(req: VLMRequest) -> JSONResponse:
    image = _normalize_image(req.image)
    if len(image) > 30_000_000:
        raise HTTPException(status_code=413, detail="image is too large (30MB base64 limit)")

    prompt = (req.prompt or VLM_DEFAULT_PROMPT).strip()
    model = req.model or VLM_MODEL
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image}},
            ],
        }],
        "temperature": 0.2,
        "max_tokens": req.max_tokens,
    }
    started = time.perf_counter()
    request = urlrequest.Request(
        VLM_BASE_URL + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_vlm_headers(),
        method="POST",
    )
    try:
        with urlrequest.urlopen(request, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        raise HTTPException(status_code=502, detail=f"VLM HTTP {exc.code}: {detail}")
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"VLM ({VLM_BASE_URL}) に接続できません: {type(exc).__name__}: {exc}",
        )

    choices = data.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str):
        raise HTTPException(status_code=502, detail=f"Unexpected VLM response: {str(data)[:500]}")

    return JSONResponse({
        "text": content,
        "model": data.get("model") or model,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
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
