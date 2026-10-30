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
from generate_report import (  # noqa: E402
    build_dashboard,
    build_network_data,
    build_network_svg,
    collect_meta,
    compute_stats,
    load_all_images,
)
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

for _mount, _dir in (("/images", IMAGES_DIR), ("/img", IMG_INDEX_DIR), ("/data", DATA_DIR),
                     ("/demo", DOCS_DIR / "demo")):
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


@app.get("/recap", response_class=HTMLResponse)
@app.get("/recap.html", response_class=HTMLResponse)
def recap_page() -> HTMLResponse:
    """Session recap page (static in docs/, also served by GitHub Pages)."""
    path = DOCS_DIR / "recap.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="recap.html not found")
    return HTMLResponse(path.read_text(encoding="utf-8"))


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


@app.get("/api/network")
def api_network(min_weight: int = Query(default=1, ge=1, le=100)) -> JSONResponse:
    data = get_data()
    return JSONResponse(build_network_data(data["all_images"], min_weight=min_weight))


@app.get("/api/network.svg")
def api_network_svg(min_weight: int = Query(default=1, ge=1, le=100)) -> Response:
    data = get_data()
    return Response(
        build_network_svg(data["all_images"], min_weight=min_weight),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


NETWORK_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hokusai Tag Network</title>
<style>
  :root { --bg:#f0f2f5; --panel:#fff; --text:#243044; --muted:#7b8794; --brand:#3949ab; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { background:linear-gradient(135deg,#1a237e,#3949ab); color:#fff; padding:18px 22px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:2px 0 0; font-size:12px; opacity:.85; }
  header a { color:#fff; }
  main { max-width:1280px; margin:0 auto; padding:18px; }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
  .panel { background:var(--panel); border-radius:14px; padding:12px; box-shadow:0 1px 6px rgba(0,0,0,.08); }
  .panel svg { width:100%; height:auto; display:block; }
  input, button { font:inherit; padding:7px 12px; border:1px solid #d5dbe6; border-radius:9px; background:#fff; }
  button { background:var(--brand); color:#fff; border-color:var(--brand); font-weight:600; cursor:pointer; }
  .muted { color:var(--muted); font-size:11px; }
  .links { display:flex; gap:14px; flex-wrap:wrap; font-size:12px; }
  .links a { color:var(--brand); font-weight:600; }
</style>
</head>
<body>
<header>
  <div style="flex:1">
    <a href="/">← Dashboard</a>
    <h1>🕸 Hokusai Tag Network</h1>
    <p>同じ画像に付与されたタグ同士を接続した共起ネットワーク（SVG）</p>
  </div>
</header>
<main>
  <form class="bar" method="get" action="/network">
    <label>最小共起数 <input type="number" name="min_weight" min="1" max="100" value="__MIN__"></label>
    <button type="submit">更新</button>
    <span class="muted">ノード＝タグ（画像数）、線＝同じ画像に付与されたタグ</span>
  </form>
  <div class="panel">__SVG__</div>
  <p class="links">
    <a href="/api/network.svg?min_weight=__MIN__">SVGを開く</a>
    <a href="/api/network?min_weight=__MIN__">JSON API</a>
    <a href="/">ダッシュボード</a>
  </p>
  <p class="muted">このページの SVG は FastAPI が plotly 非依存の純 Python で生成しています。</p>
</main>
</body>
</html>
"""


@app.get("/network", response_class=HTMLResponse)
def network_page(min_weight: int = Query(default=1, ge=1, le=100)) -> HTMLResponse:
    data = get_data()
    svg = build_network_svg(data["all_images"], min_weight=min_weight)
    html = NETWORK_PAGE.replace("__SVG__", svg).replace("__MIN__", str(min_weight))
    return HTMLResponse(html)


# JSONL Log Viewer
LOGS_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hokusai VLM Logs</title>
<style>
  :root { --bg:#f0f2f5; --panel:#fff; --text:#243044; --muted:#7b8794; --line:#e3e7ee;
          --brand:#3949ab; --brand2:#1a237e; --ok:#2e7d32; --warn:#f57f17; --err:#c62828; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { background:linear-gradient(135deg,var(--brand2),var(--brand)); color:#fff;
           padding:18px 22px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:2px 0 0; font-size:12px; opacity:.85; }
  header a { color:#fff; text-decoration:none; opacity:.9; font-size:12px; }
  header a:hover { text-decoration:underline; }
  .badge { padding:5px 12px; border-radius:999px; font-size:11px; font-weight:700; background:rgba(255,255,255,.18); }
  .badge.ok { background:var(--ok); }
  .badge.warn { background:var(--warn); color:#3a2600; }
  .badge.bad { background:var(--err); }
  main { max-width:1280px; margin:0 auto; padding:18px; }
  .panel { background:var(--panel); border-radius:14px; padding:16px; box-shadow:0 1px 6px rgba(0,0,0,.08); }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
  input, select, button { font:inherit; padding:7px 12px; border:1px solid var(--line); border-radius:8px; background:#fafbfc; }
  button { background:var(--brand); color:#fff; border-color:var(--brand); font-weight:600; cursor:pointer; }
  button:hover:not(:disabled) { background:var(--brand2); border-color:var(--brand2); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  .log-list { list-style:none; padding:0; margin:0; }
  .log-item { border-bottom:1px solid var(--line); padding:14px 0; display:grid; gap:8px; }
  .log-item:last-child { border-bottom:none; }
  .log-header { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  .log-image { font-family:ui-monospace,monospace; font-size:13px; color:var(--brand); font-weight:600; }
  .log-time { color:var(--muted); font-size:12px; }
  .log-badge { display:inline-flex; gap:6px; font-size:11px; padding:2px 8px; border-radius:6px; background:#eef1f5; }
  .log-badge.suit { background:#e8f5e9; color:#2e7d32; }
  .log-badge.cat { background:#e3f2fd; color:#1565c0; }
  .log-toggle { background:none; border:none; color:var(--brand); cursor:pointer; font-size:12px; padding:0; font-weight:600; }
  .log-toggle:hover { text-decoration:underline; }
  .log-detail { display:none; background:#0f172a; color:#e2e8f0; border-radius:10px; padding:12px; font:12px/1.55 ui-monospace,monospace; overflow:auto; max-height:400px; }
  .log-detail.open { display:block; }
  .log-raw { white-space:pre-wrap; word-break:break-word; }
  .log-img { max-width:200px; border-radius:8px; margin-top:8px; border:1px solid var(--line); }
  .muted { color:var(--muted); font-size:12px; }
  .empty { text-align:center; color:var(--muted); padding:40px; }
</style>
</head>
<body>
<header>
  <div style="flex:1">
    <a href="/">← Dashboard</a>
    <h1>📜 VLM Review Logs</h1>
    <p>JSONL レビュー履歴の閲覧・検索</p>
  </div>
  <span id="count" class="badge">読み込み中…</span>
</header>
<main>
  <div class="panel">
    <form class="bar" id="filterForm">
      <input type="search" id="q" placeholder="画像名 / subject / notes で検索" style="flex:1; min-width:200px;">
      <select id="category">
        <option value="">全カテゴリ</option>
      </select>
      <select id="minSuit">
        <option value="">適合度フィルタなし</option>
        <option value="8">8以上</option>
        <option value="6">6以上</option>
        <option value="4">4以上</option>
      </select>
      <button type="submit">絞り込み</button>
      <button type="button" id="clearBtn">クリア</button>
    </form>
    <ul id="logList" class="log-list"></ul>
    <div id="empty" class="empty" hidden>該当するログがありません</div>
    <div class="bar" style="margin-top:16px;">
      <span class="muted" id="showing">0 / 0 件</span>
      <button type="button" id="loadMore" hidden>もっと読み込む</button>
    </div>
  </div>
</main>
<script>
const $ = id => document.getElementById(id);
const logList = $('logList'), empty = $('empty'), showing = $('showing'), loadMoreBtn = $('loadMore');
const q = $('q'), category = $('category'), minSuit = $('minSuit'), countEl = $('count');

let allLogs = [];
let filteredLogs = [];
let displayedCount = 0;
const PAGE_SIZE = 50;

async function loadLogs() {
  try {
    const res = await fetch('/api/logs', { cache: 'no-store' });
    const data = await res.json();
    allLogs = data.items || [];
    populateCategories();
    applyFilter();
    countEl.textContent = allLogs.length + ' 件';
    countEl.className = 'badge ok';
  } catch (err) {
    countEl.textContent = '読み込み失敗';
    countEl.className = 'badge bad';
    console.error(err);
  }
}

function populateCategories() {
  const cats = [...new Set(allLogs.map(l => l.category).filter(Boolean))].sort();
  category.innerHTML = '<option value="">全カテゴリ</option>' +
    cats.map(c => `<option value="${c}">${c}</option>`).join('');
}

function applyFilter() {
  const query = q.value.toLowerCase().trim();
  const cat = category.value;
  const suit = parseInt(minSuit.value) || 0;
  
  filteredLogs = allLogs.filter(log => {
    if (query) {
      const haystack = (log.image + ' ' + (log.subject || '') + ' ' + (log.notes || '')).toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (cat && log.category !== cat) return false;
    if (suit && (log.suit || 0) < suit) return false;
    return true;
  });
  displayedCount = 0;
  renderLogs();
  loadMoreBtn.hidden = filteredLogs.length <= PAGE_SIZE;
}

function renderLogs(append = false) {
  if (!append) logList.innerHTML = '';
  const next = filteredLogs.slice(displayedCount, displayedCount + PAGE_SIZE);
  if (next.length === 0 && !append) {
    empty.hidden = false;
    logList.hidden = true;
  } else {
    empty.hidden = true;
    logList.hidden = false;
    for (const log of next) {
      logList.appendChild(createLogElement(log));
    }
    displayedCount += next.length;
  }
  showing.textContent = `${displayedCount} / ${filteredLogs.length} 件`;
  loadMoreBtn.hidden = displayedCount >= filteredLogs.length;
}

function createLogElement(log) {
  const li = document.createElement('li');
  li.className = 'log-item';
  
  const parsed = typeof log.response === 'string' ? JSON.parse(log.response) : log.response;
  const suit = parsed.training_suitability || parsed.suitability || log.suit || 0;
  const cat = parsed.category || log.category || '';
  
  li.innerHTML = `
    <div class="log-header">
      <span class="log-image">${log.image}</span>
      <span class="log-badge suit">適合度: ${suit}/10</span>
      ${cat ? `<span class="log-badge cat">${cat}</span>` : ''}
      <span class="log-time">${log.timestamp || ''}</span>
      <button class="log-toggle" onclick="toggleDetail(this)">詳細 ▼</button>
    </div>
    <div class="log-detail">
      <div class="log-raw">${escapeHtml(JSON.stringify(parsed, null, 2))}</div>
      <img class="log-img" src="/images/${log.image}" alt="${log.image}" loading="lazy" onerror="this.style.display='none'"">
    </div>
  `;
  return li;
}

function toggleDetail(btn) {
  const detail = btn.closest('.log-item').querySelector('.log-detail');
  const isOpen = detail.classList.toggle('open');
  btn.textContent = isOpen ? '詳細 ▲' : '詳細 ▼';
}

function escapeHtml(text) {
  return text.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');
}

$('filterForm').addEventListener('submit', e => { e.preventDefault(); applyFilter(); });
$('clearBtn').onclick = () => { q.value = ''; category.value = ''; minSuit.value = ''; applyFilter(); };
loadMoreBtn.onclick = () => renderLogs(true);

loadLogs();
</script>
</body>
</html>
"""


@app.get("/logs", response_class=HTMLResponse)
@app.get("/logs/", response_class=HTMLResponse)
def logs_page() -> HTMLResponse:
    return HTMLResponse(LOGS_PAGE)


@app.get("/api/logs")
def api_logs() -> JSONResponse:
    if not JSONL_PATH.exists():
        return JSONResponse({"items": [], "total": 0})
    items = []
    with JSONL_PATH.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                # Parse response JSON string if needed
                parsed = {}
                if isinstance(record.get('response'), str):
                    try:
                        parsed = json.loads(record['response'])
                    except json.JSONDecodeError:
                        parsed = {}
                items.append({
                    "image": record.get('image', ''),
                    "response": record.get('response', ''),
                    "subject": parsed.get('subject', ''),
                    "category": parsed.get('category', ''),
                    "suit": parsed.get('training_suitability') or parsed.get('suitability', 0),
                    "notes": parsed.get('notes', ''),
                    "timestamp": record.get('timestamp', ''),
                })
            except json.JSONDecodeError:
                continue
    return JSONResponse({"items": items, "total": len(items)})


# Query / Search Page
QUERY_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hokusai VLM Query</title>
<style>
  :root { --bg:#f0f2f5; --panel:#fff; --text:#243044; --muted:#7b8794; --line:#e3e7ee;
          --brand:#3949ab; --brand2:#1a237e; --ok:#2e7d32; --warn:#f57f17; --err:#c62828; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { background:linear-gradient(135deg,var(--brand2),var(--brand)); color:#fff;
           padding:18px 22px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:2px 0 0; font-size:12px; opacity:.85; }
  header a { color:#fff; text-decoration:none; opacity:.9; font-size:12px; }
  header a:hover { text-decoration:underline; }
  .badge { padding:5px 12px; border-radius:999px; font-size:11px; font-weight:700; background:rgba(255,255,255,.18); }
  .badge.ok { background:var(--ok); }
  .badge.warn { background:var(--warn); color:#3a2600; }
  .badge.bad { background:var(--err); }
  main { max-width:1280px; margin:0 auto; padding:18px; display:grid; gap:16px; grid-template-columns: 320px 1fr; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  .panel { background:var(--panel); border-radius:14px; padding:16px; box-shadow:0 1px 6px rgba(0,0,0,.08); }
  .panel h2 { font-size:13px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); margin:0 0 12px; }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
  input, select, button { font:inherit; padding:7px 12px; border:1px solid var(--line); border-radius:8px; background:#fafbfc; }
  button { background:var(--brand); color:#fff; border-color:var(--brand); font-weight:600; cursor:pointer; }
  button:hover:not(:disabled) { background:var(--brand2); border-color:var(--brand2); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  button.secondary { background:#fff; color:var(--brand); }
  .field { display:flex; flex-direction:column; gap:6px; margin-bottom:12px; }
  .field label { font-size:12px; color:var(--muted); font-weight:600; }
  .field input[type=search], .field select { padding:8px 12px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { padding:4px 10px; border-radius:999px; font-size:11px; background:#eef1f5; cursor:pointer; transition:all .15s; }
  .chip:hover { background:var(--brand); color:#fff; }
  .chip.active { background:var(--brand); color:#fff; }
  .chip.suit { background:#e8f5e9; color:#2e7d32; }
  .chip.suit.active { background:#2e7d32; color:#fff; }
  .chip.cat { background:#e3f2fd; color:#1565c0; }
  .chip.cat.active { background:#1565c0; color:#fff; }
  .results { display:grid; gap:12px; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
  .result-card { background:var(--panel); border-radius:12px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); transition:transform .15s, box-shadow .15s; }
  .result-card:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,.1); }
  .result-img { width:100%; aspect-ratio:4/3; object-fit:cover; background:#eef1f5; }
  .result-body { padding:12px; display:grid; gap:6px; }
  .result-title { font-weight:600; font-size:13px; color:var(--text); }
  .result-meta { display:flex; gap:8px; flex-wrap:wrap; font-size:11px; }
  .result-suit { background:#e8f5e9; color:#2e7d32; padding:2px 8px; border-radius:6px; font-weight:600; }
  .result-cat { background:#e3f2fd; color:#1565c0; padding:2px 8px; border-radius:6px; }
  .result-subject { font-size:12px; color:var(--muted); line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .result-notes { font-size:11px; color:var(--muted); line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .empty { text-align:center; color:var(--muted); padding:60px 20px; grid-column:1/-1; }
  .stats { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:16px; padding:12px; background:#fafbfc; border-radius:10px; }
  .stat { display:flex; flex-direction:column; }
  .stat-value { font-size:24px; font-weight:700; color:var(--brand); line-height:1; }
  .stat-label { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
  .sort-bar { display:flex; gap:10px; align-items:center; margin-bottom:16px; padding:12px; background:#fafbfc; border-radius:10px; }
  .sort-bar select { flex:1; max-width:200px; }
  .range-inputs { display:flex; gap:8px; align-items:center; }
  .range-inputs input { width:80px; }
</style>
</head>
<body>
<header>
  <div style="flex:1">
    <a href="/">← Dashboard</a>
    <h1>🔍 VLM Query Builder</h1>
    <p>レビュー検索・フィルタ・ソート</p>
  </div>
  <span id="totalCount" class="badge">読み込み中…</span>
</header>
<main>
  <aside class="panel" style="position:sticky; top:20px; max-height:calc(100vh - 100px); overflow:auto;">
    <h2>Filters</h2>
    
    <div class="field">
      <label>フリーワード検索</label>
      <input type="search" id="q" placeholder="画像名 / subject / notes / category">
    </div>

    <div class="field">
      <label>カテゴリ</label>
      <div class="chips" id="catChips"><span class="muted">読み込み中…</span></div>
      <input type="hidden" id="category" value="">
    </div>

    <div class="field">
      <label>適合度 (training_suitability)</label>
      <div class="range-inputs">
        <input type="number" id="minSuit" min="0" max="10" placeholder="Min" step="0.5">
        <span>〜</span>
        <input type="number" id="maxSuit" min="0" max="10" placeholder="Max" step="0.5">
      </div>
      <div class="chips" style="margin-top:8px;">
        <span class="chip suit" data-min="7" data-max="10">7-10 (優秀)</span>
        <span class="chip suit" data-min="5" data-max="6.9">5-6.9 (普通)</span>
        <span class="chip suit" data-min="0" data-max="4.9">0-4.9 (要注意)</span>
      </div>
    </div>

    <div class="field">
      <label>画像ありのみ</label>
      <div class="chips">
        <span class="chip" id="hasImageChip" data-val="true">画像あり</span>
        <span class="chip" id="noImageChip" data-val="false">画像なし</span>
      </div>
      <input type="hidden" id="hasImage" value="">
    </div>

    <div class="field">
      <label>巻 (Volume)</label>
      <div class="chips" id="volChips"><span class="muted">読み込み中…</span></div>
      <input type="hidden" id="volume" value="">
    </div>

    <button id="clearAll" class="secondary" style="width:100%; margin-top:8px;">すべてクリア</button>
  </aside>

  <section class="panel">
    <div class="stats">
      <div class="stat"><span id="statTotal" class="stat-value">0</span><span class="stat-label">総件数</span></div>
      <div class="stat"><span id="statFiltered" class="stat-value">0</span><span class="stat-label">絞込後</span></div>
      <div class="stat"><span id="statAvgSuit" class="stat-value">0</span><span class="stat-label">平均適合度</span></div>
      <div class="stat"><span id="statVolumes" class="stat-value">0</span><span class="stat-label">巻数</span></div>
    </div>

    <div class="sort-bar">
      <label>並び順
        <select id="sortBy">
          <option value="suit_desc">適合度 降順</option>
          <option value="suit_asc">適合度 昇順</option>
          <option value="image_asc">画像名 昇順</option>
          <option value="image_desc">画像名 降順</option>
          <option value="category">カテゴリ</option>
          <option value="volume">巻番号</option>
        </select>
      </label>
      <span class="muted" id="showingInfo"></span>
    </div>

    <div id="results" class="results"></div>
    <div id="empty" class="empty" hidden>該当する結果がありません</div>

    <div class="bar" style="margin-top:16px; justify-content:center;">
      <button id="loadMore" class="secondary" hidden>もっと読み込む (50件)</button>
    </div>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
const resultsEl = $('results'), emptyEl = $('empty'), loadMoreBtn = $('loadMore');
const q = $('q'), categoryEl = $('category'), minSuit = $('minSuit'), maxSuit = $('maxSuit');
const hasImageEl = $('hasImage'), volumeEl = $('volume'), sortBy = $('sortBy');
const totalCountEl = $('totalCount'), statTotal = $('statTotal'), statFiltered = $('statFiltered');
const statAvgSuit = $('statAvgSuit'), statVolumes = $('statVolumes'), showingInfo = $('showingInfo');

let allItems = [];
let filteredItems = [];
let displayedCount = 0;
const PAGE_SIZE = 50;

async function loadData() {
  try {
    const res = await fetch('/api/reviews?limit=5000', { cache: 'no-store' });
    const data = await res.json();
    allItems = data.items || [];
    buildChips();
    applyFilter();
    updateStats();
    totalCountEl.textContent = allItems.length + ' 件';
    totalCountEl.className = 'badge ok';
  } catch (err) {
    totalCountEl.textContent = '読み込み失敗';
    totalCountEl.className = 'badge bad';
    console.error(err);
  }
}

function buildChips() {
  // Categories
  const cats = [...new Set(allItems.map(i => i.category).filter(Boolean))].sort();
  $('catChips').innerHTML = cats.map(c => 
    `<span class="chip cat" data-cat="${escapeHtml(c)}">${escapeHtml(c)}</span>`
  ).join('') || '<span class="muted">なし</span>';
  
  // Volumes
  const vols = [...new Set(allItems.map(i => {
    const m = i.image.match(/^(\d+)_/);
    return m ? `Vol ${m[1]}` : null;
  }).filter(Boolean))].sort((a,b) => parseInt(a.replace('Vol ','')) - parseInt(b.replace('Vol ','')));
  $('volChips').innerHTML = vols.map(v => 
    `<span class="chip" data-vol="${escapeHtml(v)}">${escapeHtml(v)}</span>`
  ).join('') || '<span class="muted">なし</span>';

  // Chip click handlers
  document.querySelectorAll('.chip[data-cat]').forEach(el => {
    el.onclick = () => { el.classList.toggle('active'); updateCategoryInput(); applyFilter(); };
  });
  document.querySelectorAll('.chip[data-vol]').forEach(el => {
    el.onclick = () => { el.classList.toggle('active'); updateVolumeInput(); applyFilter(); };
  });
  document.querySelectorAll('.chip.suit[data-min]').forEach(el => {
    el.onclick = () => {
      document.querySelectorAll('.chip.suit[data-min]').forEach(c => c.classList.remove('active'));
      el.classList.add('active');
      minSuit.value = el.dataset.min;
      maxSuit.value = el.dataset.max;
      applyFilter();
    };
  });
  $('hasImageChip').onclick = () => {
    $('hasImageChip').classList.toggle('active');
    $('noImageChip').classList.remove('active');
    hasImageEl.value = $('hasImageChip').classList.contains('active') ? 'true' : '';
    applyFilter();
  };
  $('noImageChip').onclick = () => {
    $('noImageChip').classList.toggle('active');
    $('hasImageChip').classList.remove('active');
    hasImageEl.value = $('noImageChip').classList.contains('active') ? 'false' : '';
    applyFilter();
  };
}

function updateCategoryInput() {
  const active = [...document.querySelectorAll('.chip.cat.active')].map(el => el.dataset.cat);
  categoryEl.value = active.join(',');
}
function updateVolumeInput() {
  const active = [...document.querySelectorAll('.chip[data-vol].active')].map(el => el.dataset.vol);
  volumeEl.value = active.join(',');
}

function applyFilter() {
  const query = q.value.toLowerCase().trim();
  const cats = categoryEl.value ? categoryEl.value.split(',') : [];
  const minS = parseFloat(minSuit.value) || 0;
  const maxS = parseFloat(maxSuit.value) || 10;
  const hasImg = hasImageEl.value;
  const vols = volumeEl.value ? volumeEl.value.split(',') : [];

  filteredItems = allItems.filter(item => {
    if (query) {
      const haystack = (item.image + ' ' + (item.subject || '') + ' ' + (item.notes || '') + ' ' + (item.category || '')).toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (cats.length && !cats.includes(item.category)) return false;
    const suit = item.suit || 0;
    if (suit < minS || suit > maxS) return false;
    if (hasImg === 'true' && !item.image) return false;
    if (hasImg === 'false' && item.image) return false;
    if (vols.length) {
      const m = item.image.match(/^(\d+)_/);
      const vol = m ? `Vol ${m[1]}` : null;
      if (!vol || !vols.includes(vol)) return false;
    }
    return true;
  });

  sortResults();
  displayedCount = 0;
  renderResults();
  loadMoreBtn.hidden = filteredItems.length <= PAGE_SIZE;
  updateShowingInfo();
}

function sortResults() {
  const by = sortBy.value;
  filteredItems.sort((a, b) => {
    if (by === 'suit_desc') return (b.suit || 0) - (a.suit || 0);
    if (by === 'suit_asc') return (a.suit || 0) - (b.suit || 0);
    if (by === 'image_asc') return a.image.localeCompare(b.image);
    if (by === 'image_desc') return b.image.localeCompare(a.image);
    if (by === 'category') return (a.category || '').localeCompare(b.category || '');
    if (by === 'volume') {
      const av = parseInt((a.image.match(/^(\d+)_/) || [0])[1]) || 0;
      const bv = parseInt((b.image.match(/^(\d+)_/) || [0])[1]) || 0;
      return av - bv;
    }
    return 0;
  });
}

function renderResults(append = false) {
  if (!append) resultsEl.innerHTML = '';
  const next = filteredItems.slice(displayedCount, displayedCount + PAGE_SIZE);
  if (next.length === 0 && !append) {
    emptyEl.hidden = false;
    resultsEl.hidden = true;
  } else {
    emptyEl.hidden = true;
    resultsEl.hidden = false;
    for (const item of next) {
      resultsEl.appendChild(createCard(item));
    }
    displayedCount += next.length;
  }
  updateShowingInfo();
  loadMoreBtn.hidden = displayedCount >= filteredItems.length;
}

function createCard(item) {
  const div = document.createElement('div');
  div.className = 'result-card';
  const suit = item.suit || 0;
  const cat = item.category || '';
  const volMatch = item.image.match(/^(\d+)_/);
  const vol = volMatch ? `Vol ${volMatch[1]}` : '';
  div.innerHTML = `
    <img class="result-img" src="/images/${item.image}" alt="${item.image}" loading="lazy" onerror="this.style.display='none'">
    <div class="result-body">
      <div class="result-title">${escapeHtml(item.image)}${vol ? ' <span class=\"muted\">(' + vol + ')</span>' : ''}</div>
      <div class="result-meta">
        <span class="result-suit">適合度: ${suit}/10</span>
        ${cat ? `<span class="result-cat">${escapeHtml(cat)}</span>` : ''}
      </div>
      ${item.subject ? `<div class="result-subject">${escapeHtml(item.subject)}</div>` : ''}
      ${item.notes ? `<div class="result-notes">${escapeHtml(item.notes)}</div>` : ''}
    </div>
  `;
  div.onclick = () => window.open('/logs', '_blank');
  return div;
}

function updateStats() {
  const suits = allItems.map(i => i.suit || 0).filter(s => s > 0);
  const avg = suits.length ? (suits.reduce((a,b)=>a+b,0)/suits.length).toFixed(1) : 0;
  const vols = new Set(allItems.map(i => {
    const m = i.image.match(/^(\d+)_/);
    return m ? m[1] : null;
  }).filter(Boolean));
  statTotal.textContent = allItems.length;
  statAvgSuit.textContent = avg;
  statVolumes.textContent = vols.size;
}

function updateShowingInfo() {
  showingInfo.textContent = `表示: ${displayedCount} / ${filteredItems.length} 件`;
  statFiltered.textContent = filteredItems.length;
}

function escapeHtml(text) {
  return String(text).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"');
}

// Event listeners
q.addEventListener('input', () => { clearTimeout(window._filterTimer); window._filterTimer = setTimeout(applyFilter, 200); });
minSuit.addEventListener('change', applyFilter);
maxSuit.addEventListener('change', applyFilter);
sortBy.addEventListener('change', () => { displayedCount = 0; renderResults(); });
loadMoreBtn.onclick = () => renderResults(true);
$('clearAll').onclick = () => {
  q.value = '';
  categoryEl.value = '';
  minSuit.value = '';
  maxSuit.value = '';
  hasImageEl.value = '';
  volumeEl.value = '';
  document.querySelectorAll('.chip.active').forEach(c => c.classList.remove('active'));
  applyFilter();
};

loadData();
</script>
</body>
</html>
"""


@app.get("/query", response_class=HTMLResponse)
@app.get("/query/", response_class=HTMLResponse)
def query_page() -> HTMLResponse:
    return HTMLResponse(QUERY_PAGE)


# Links / Index Page
LINKS_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hokusai VLM - Links</title>
<style>
  :root { --bg:#f0f2f5; --panel:#fff; --text:#243044; --muted:#7b8794; --line:#e3e7ee;
          --brand:#3949ab; --brand2:#1a237e; --ok:#2e7d32; --warn:#f57f17; --err:#c62828; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { background:linear-gradient(135deg,var(--brand2),var(--brand)); color:#fff;
           padding:24px 22px; text-align:center; }
  header h1 { margin:0 0 8px; font-size:24px; }
  header p { margin:0; opacity:.9; font-size:14px; }
  main { max-width:800px; margin:0 auto; padding:24px 18px; }
  .grid { display:grid; gap:16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
  .card { background:var(--panel); border-radius:14px; padding:20px; box-shadow:0 1px 6px rgba(0,0,0,.08);
          transition:transform .15s, box-shadow .15s; border:1px solid var(--line); }
  .card:hover { transform:translateY(-2px); box-shadow:0 6px 20px rgba(0,0,0,.1); }
  .card h2 { margin:0 0 8px; font-size:16px; display:flex; align-items:center; gap:8px; }
  .card p { margin:0 0 16px; color:var(--muted); font-size:13px; }
  .btn { display:inline-block; padding:10px 18px; background:var(--brand); color:#fff;
         border-radius:8px; font-weight:600; text-decoration:none; transition:background .15s; }
  .btn:hover { background:var(--brand2); color:#fff; text-decoration:none; }
  .btn.secondary { background:#fff; color:var(--brand); border:1px solid var(--brand); }
  .btn.secondary:hover { background:var(--brand); color:#fff; }
  .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700; }
  .badge.new { background:#e8f5e9; color:#2e7d32; }
  .badge.hot { background:#fff3e0; color:#e65100; }
  .btns { display:flex; gap:8px; flex-wrap:wrap; }
  .status { display:flex; gap:16px; justify-content:center; margin-bottom:24px; flex-wrap:wrap; }
  .status-item { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); }
  .status-dot { width:8px; height:8px; border-radius:50%; background:var(--ok); }
  footer { text-align:center; padding:24px; color:var(--muted); font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>🎨 Hokusai VLM Dashboard</h1>
  <p>全機能へのクイックアクセス</p>
</header>
<main>
  <div class="status">
    <span class="status-item"><span class="status-dot"></span>Server: Running</span>
    <span class="status-item"><span class="status-dot"></span>VLM: Connected</span>
    <span class="status-item"><span class="status-dot"></span>Model: tempura-qwen2.5-vl-3b</span>
  </div>

  <div class="grid">
    <div class="card">
      <h2>🔍 <span class="badge new">NEW</span> Query Builder</h2>
      <p>高機能検索・フィルタ・ソート・サムネイルグリッド</p>
      <div class="btns">
        <a href="/query" class="btn">開く</a>
        <a href="/api/reviews?limit=10" class="btn secondary" target="_blank">APIテスト</a>
      </div>
    </div>

    <div class="card">
      <h2>📜 <span class="badge">Logs Viewer</span></h2>
      <p>JSONL全履歴・詳細表示・JSON整形・画像サムネイル</p>
      <div class="btns">
        <a href="/logs" class="btn">開く</a>
        <a href="/api/logs" class="btn secondary" target="_blank">APIテスト</a>
      </div>
    </div>

    <div class="card">
      <h2>📷 <span class="badge hot">VLM Camera Demo</span></h2>
      <p>カメラ撮影/画像アップロード → VLM解析</p>
      <div class="btns">
        <a href="/vlm" class="btn">開く</a>
        <a href="/api/vlm/health" class="btn secondary" target="_blank">Health Check</a>
      </div>
      <p style="margin-top:12px; font-size:12px; color:var(--muted);">
        プリセット: LoRAレビュー / 日本語説明 / OCR / 年齢推定 / <b>年齢・動作・場所(日/英)</b> / <b>踊り判定</b>
      </p>
    </div>

    <div class="card">
      <h2>📊 Dashboard</h2>
      <p>KPIカード・グラフ・タグネットワーク・詳細ビュー</p>
      <div class="btns">
        <a href="/" class="btn">開く</a>
        <a href="/api/stats" class="btn secondary" target="_blank">APIテスト</a>
      </div>
    </div>

    <div class="card">
      <h2>🕸 Tag Network</h2>
      <p>タグ共起ネットワーク（SVG・インタラクティブ）</p>
      <div class="btns">
        <a href="/network" class="btn">開く</a>
        <a href="/api/network" class="btn secondary" target="_blank">APIテスト</a>
      </div>
    </div>

    <div class="card">
      <h2>📚 Volume Viewer</h2>
      <p>巻メタデータ・ページ一覧</p>
      <div class="btns">
        <a href="/viewer" class="btn">開く</a>
        <a href="/api/metadata" class="btn secondary" target="_blank">APIテスト</a>
      </div>
    </div>

    <div class="card">
      <h2>🏥 Health & Debug</h2>
      <p>システム状態確認</p>
      <div class="btns">
        <a href="/healthz" class="btn secondary" target="_blank">Basic Health</a>
        <a href="/api/vlm/health" class="btn secondary" target="_blank">VLM Health</a>
        <a href="/api/health" class="btn secondary" target="_blank">Dashboard Health</a>
      </div>
    </div>
  </div>
</main>
<footer>
  Hokusai Manga VLM Dashboard · Powered by FastAPI + plotly.py
</footer>
</body>
</html>
"""


@app.get("/links", response_class=HTMLResponse)
@app.get("/links/", response_class=HTMLResponse)
@app.get("/index", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def links_page() -> HTMLResponse:
    return HTMLResponse(LINKS_PAGE)


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
