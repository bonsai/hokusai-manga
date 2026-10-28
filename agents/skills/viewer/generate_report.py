#!/usr/bin/env python3
"""
Hokusai VLM Review Dashboard — Interactive report with Plotly charts, views, filters.
View modes: GLANCE, GRID, LIST, GROUP, GRAPH.
Data source: SQLite/JSONL → embedded JSON + Plotly JS charts.
No FastAPI required — pure HTML+JS with embedded data.
"""
import json
import sqlite3
import re
import base64
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict, OrderedDict

# ── JSON extraction helpers ─────────────────────────────────────────────

def extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()

    def _try(t: str) -> dict | None:
        try:
            d = json.loads(t)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
        fixed = re.sub(r'(\"|\})\s*\n\s*\"', r'\1,\n"', t)
        try:
            d = json.loads(fixed)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
        m = re.search(r'```(?:json)?\s*({.+?})\s*```', t, re.DOTALL)
        if m:
            for s in [m.group(1), re.sub(r'(\"|\})\s*\n\s*\"', r'\1,\n"', m.group(1))]:
                try:
                    d = json.loads(s)
                    if isinstance(d, dict):
                        return d
                except Exception:
                    pass
        idx = t.find('{')
        if idx >= 0:
            for s in [t[idx:], re.sub(r'(\"|\})\s*\n\s*\"', r'\1,\n"', t[idx:])]:
                try:
                    d = json.loads(s)
                    if isinstance(d, dict):
                        return d
                except Exception:
                    pass
        return None

    return _try(text)


def _normalize(data: dict) -> dict:
    cat = data.get("category", "unknown")
    if isinstance(cat, str) and "|" in cat:
        data["_raw_category"] = cat
        data["category"] = cat.split("|")[0]
    return data


# ── Data loaders ───────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> list[dict]:
    reviews: list[dict] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line.strip())
            except Exception:
                continue
            if "response" not in entry:
                continue
            data = extract_json(entry["response"])
            if not data or "subject" not in data:
                continue
            data["image"] = entry["image"]
            data["_raw_response"] = entry["response"]
            data = _normalize(data)
            img = data["image"]
            if img not in seen:
                seen.add(img)
                reviews.append(data)
    return reviews


def _load_db(path: Path) -> list[dict]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT image, response FROM reviews WHERE error IS NULL")
    reviews: list[dict] = []
    seen: set[str] = set()
    for row in cur.fetchall():
        data = extract_json(row["response"])
        if not data or "subject" not in data:
            continue
        data["image"] = row["image"]
        data["_raw_response"] = row["response"]
        data = _normalize(data)
        img = data["image"]
        if img not in seen:
            seen.add(img)
            reviews.append(data)
    conn.close()
    return reviews


def load_reviews(jsonl_path: Path, db_path: Path) -> list[dict]:
    if jsonl_path.exists():
        r = _load_jsonl(jsonl_path)
        if r:
            return r
    if db_path.exists():
        r = _load_db(db_path)
        if r:
            return r
    return []


def load_errors(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT image, error FROM reviews WHERE error IS NOT NULL")
    errors = [{"image": r[0], "error": r[1] or "Read timed out"} for r in cur.fetchall()]
    conn.close()
    return errors


# ── Statistics ─────────────────────────────────────────────────────────

def compute_stats(reviews: list[dict]) -> dict:
    cats: dict[str, int] = {}
    suits: list[int] = []
    q: dict[str, list[int]] = defaultdict(list)

    for r in reviews:
        c = r.get("category", "unknown")
        cats[c] = cats.get(c, 0) + 1
        s = r.get("training_suitability")
        if s is not None:
            suits.append(int(s))
        lq = r.get("lora_quality", {})
        for k in ("linework", "contrast", "composition", "artifact_free"):
            v = lq.get(k)
            if v is not None:
                q[k].append(v)

    avg_s = round(sum(suits) / len(suits), 1) if suits else 0
    med_s = sorted(suits)[len(suits) // 2] if suits else 0

    avg_q = {k: round(sum(v) / len(v), 2) for k, v in q.items()}
    suit_dist = dict(Counter(suits))

    return {
        "categories": cats,
        "avg_suitability": avg_s,
        "median_suitability": med_s,
        "quality": avg_q,
        "suit_dist": suit_dist,
        "total": len(reviews),
    }


# ── HTML helpers ──────────────────────────────────────────────────────

def img_tag(name: str, img_dir: str | None, size: str = "80px") -> str:
    if not img_dir:
        return (
            f'<div style="width:{size};height:{size};background:#eee;border-radius:6px;'
            f'display:flex;align-items:center;justify-content:center;color:#999;font-size:10px">N/A</div>'
        )
    src = f"{img_dir}/{name}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
        '<rect width="100%" height="100%" fill="#ffebee"/>'
        '<text x="50%" y="50%" fill="#c62828" font-size="11" '
        'text-anchor="middle" dominant-baseline="middle">ERR</text></svg>'
    )
    fallback = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (
        f'<img src="{src}" alt="{name}" style="width:{size};height:{size};object-fit:cover;'
        f'border-radius:6px;border:1px solid #ddd;background:#fafafa;" loading="lazy" '
        f"onerror=\"this.onerror=null;this.src='{fallback}'\">"
    )


def _suit_color(s: int) -> str:
    if s >= 8:
        return "#2e7d32"
    if s >= 6:
        return "#f57f17"
    return "#c62828"


CAT_CSS = {
    "landscape": "#2e7d32",
    "daily_life": "#e65100",
    "yokai": "#c2185b",
    "nature": "#1b5e20",
    "calligraphy": "#7b1fa2",
    "figure": "#1565c0",
    "action": "#f57c00",
    "narrative": "#0d47a1",
    "animals": "#388e3c",
    "unknown": "#757575",
    "error": "#c62828",
}

# Plotly 2.27 does not try to load maplibre CSS from unpkg.com.
PLOTLY_JS_CDN = "https://cdn.plot.ly/plotly-2.27.0.min.js"


def _fig_html(fig, div_id: str) -> str:
    """Render a plotly.py figure to an embeddable div + init script."""
    import plotly.io as pio

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter,sans-serif", "size": 12, "color": "#555"},
        margin={"t": 20, "b": 40, "l": 50, "r": 20},
        height=400,
        autosize=True,
    )
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={"responsive": True, "displayModeBar": False},
    )


def build_figures(
    stats: dict,
    tag_labels: list[str],
    tag_values: list[int],
    tag_colors: list[str],
    vol_labels: list[str],
    vol_values: list[int],
) -> dict[str, str]:
    """Build all dashboard charts with plotly.py (no client-side chart code)."""
    import plotly.graph_objects as go

    cat_labels = list(stats["categories"].keys())
    cat_values = list(stats["categories"].values())
    cat_colors = [CAT_CSS.get(c, "#999") for c in cat_labels]

    suit_labels = [str(s) for s in range(1, 11)]
    suit_colors = ["#2e7d32" if s >= 8 else "#f57f17" if s >= 6 else "#c62828" for s in range(1, 11)]
    suit_values = [stats["suit_dist"].get(s, 0) for s in range(1, 11)]

    qual_keys = ["linework", "contrast", "composition", "artifact_free"]
    qual_labels = ["Line", "Contrast", "Composition", "Artifact Free"]
    qual_values = [round(stats["quality"].get(k, 0), 2) for k in qual_keys]

    dist_labels, dist_values, dist_colors = [], [], []
    for lo, hi, label, color in [(8, 10, "8-10 (Good)", "#2e7d32"), (6, 7, "6-7 (Avg)", "#f57f17"), (0, 5, "0-5 (Poor)", "#c62828")]:
        cnt = sum(v for k, v in stats["suit_dist"].items() if lo <= k <= hi)
        if cnt:
            dist_labels.append(label)
            dist_values.append(cnt)
            dist_colors.append(color)

    fig_cat = go.Figure(go.Pie(
        labels=cat_labels, values=cat_values, hole=0.5,
        marker={"colors": cat_colors},
    ))
    fig_cat.update_layout(showlegend=True, legend={"font": {"size": 11}})

    fig_suit = go.Figure(go.Bar(
        x=suit_labels, y=suit_values, marker_color=suit_colors,
        text=suit_values, textposition="auto",
    ))
    fig_suit.update_layout(xaxis={"title": "Suitability"}, yaxis={"title": "Count", "rangemode": "tozero"})

    fig_qual = go.Figure(go.Scatterpolar(
        r=qual_values + qual_values[:1],
        theta=qual_labels + qual_labels[:1],
        fill="toself", fillcolor="rgba(57,73,171,.15)",
        line={"color": "#3949ab"},
    ))
    fig_qual.update_layout(polar={"radialaxis": {"range": [0, 10]}})

    fig_dist = go.Figure(go.Pie(
        labels=dist_labels, values=dist_values, hole=0.45,
        marker={"colors": dist_colors},
    ))
    fig_dist.update_layout(showlegend=True, legend={"font": {"size": 11}})

    fig_vol = go.Figure(go.Bar(
        x=vol_labels, y=vol_values, marker_color="#3949ab",
        text=vol_values, textposition="auto",
    ))
    fig_vol.update_layout(xaxis={"title": "Volume"}, yaxis={"title": "Images", "rangemode": "tozero"})

    fig_tag = go.Figure(go.Bar(
        x=tag_values, y=tag_labels, orientation="h",
        marker_color=tag_colors, text=tag_values, textposition="auto",
    ))
    fig_tag.update_layout(
        margin={"l": 120, "r": 20, "t": 20, "b": 40},
        xaxis={"title": "Images", "rangemode": "tozero"},
        yaxis={"automargin": True},
    )

    return {
        "cat": _fig_html(fig_cat, "chCat"),
        "suit": _fig_html(fig_suit, "chSuit"),
        "qual": _fig_html(fig_qual, "chQual"),
        "dist": _fig_html(fig_dist, "chDist"),
        "vol": _fig_html(fig_vol, "chVol"),
        "tag": _fig_html(fig_tag, "chTag"),
    }


# ── Dashboard builder ──────────────────────────────────────────────────

def collect_meta(all_images: list[dict]) -> tuple[Counter, Counter, list[dict]]:
    """Return tag counts, volume counts, and per-image detail records."""
    tag_counts: Counter = Counter()
    vol_counts: Counter = Counter()
    detail_data: list[dict] = []
    for r in all_images:
        raw_cat = r.get("_raw_category") or r.get("category", "unknown")
        tags = [t.strip() for t in str(raw_cat).split("|") if t.strip()]
        tag_counts.update(tags)
        m = re.match(r"^(\d{6})_", r["image"])
        if m:
            vol_counts[int(m.group(1)) - 851645] += 1
        detail_data.append({
            "image": r["image"],
            "subject": r.get("subject") or "",
            "category": r.get("category", "unknown"),
            "tags": tags,
            "style_notes": r.get("style_notes") or "",
            "notes": r.get("error") or r.get("notes") or "",
            "suit": r.get("training_suitability", 0),
            "quality": r.get("lora_quality") or {},
            "error": bool(r.get("_error")),
            "raw": r.get("_raw_response") or "",
        })
    return tag_counts, vol_counts, detail_data


def load_all_images(jsonl_path: Path, db_path: Path) -> tuple[list[dict], list[dict]]:
    """Load reviews and timeout errors into the same ordering used by the dashboard."""
    reviews = load_reviews(jsonl_path, db_path)
    errors = load_errors(db_path) if db_path.exists() else []
    all_images = list(reviews)
    for e in errors:
        all_images.append({
            "image": e["image"],
            "subject": "⚠️ TIMEOUT",
            "category": "error",
            "training_suitability": 0,
            "lora_quality": {},
            "notes": e.get("error") or "Read timed out",
            "_error": True,
        })
    return all_images, errors


def build_dashboard(
    all_images: list[dict],
    errors: list[dict],
    img_dir: str,
    output: Path | None,
    title: str = "Hokusai Dashboard",
    plotly_js: str = PLOTLY_JS_CDN,
    vlm_demo_url: str | None = None,
) -> str:
    total = len(all_images)
    err_count = len(errors)
    err_pct = round(err_count / total * 100, 1) if total else 0

    stats = compute_stats([i for i in all_images if not i.get("_error")])

    # ── metadata aggregates (tags / volumes) ──
    tag_counts, vol_counts, detail_data = collect_meta(all_images)

    tag_labels = [t for t, _ in tag_counts.most_common()]
    tag_values = [tag_counts[t] for t in tag_labels]
    tag_colors = [CAT_CSS.get(t, "#999") for t in tag_labels]
    vol_labels = [f"Vol {v}" for v in sorted(vol_counts)]
    vol_values = [vol_counts[v] for v in sorted(vol_counts)]

    def _js(obj) -> str:
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    detail_json = _js(detail_data)
    img_json = _js(img_dir or "")
    cat_json = _js(CAT_CSS)

    # ── category options ──
    cat_opts = "".join(
        f'<option value="{c}">{c.replace("_", " ").title()}</option>'
        for c in sorted(stats["categories"])
    )
    if err_count:
        cat_opts += '<option value="error">⚠️ Errors</option>'

    # ── card renderer (Glance sample + full Grid) ──
    def card_html(i: int, r: dict) -> str:
        is_err = r.get("_error", False)
        cat = r.get("category", "unknown")
        suit = r.get("training_suitability", 0)
        lq = r.get("lora_quality", {})
        qs = f"{lq.get('linework','')}/{lq.get('contrast','')}/{lq.get('composition','')}/{lq.get('artifact_free','')}"
        subj = (r.get("subject") or "")[:80]
        clr = _suit_color(suit)
        border = "border:2px solid #e74c3c;" if is_err else ""
        return (
            f'<div class="img-card" data-i="{i}" data-cat="{cat}" data-suit="{suit}" data-name="{r["image"]}" '
            f'style="cursor:pointer;{border}" onclick="openDetail({i})" title="詳細を開く">'
            f'<div style="text-align:center;padding:8px">{img_tag(r["image"], img_dir, "150px")}</div>'
            f'<div style="padding:0 10px 10px">'
            f'<div style="font-weight:bold;font-size:11px;margin-bottom:4px">{r["image"]}</div>'
            f'<div style="font-size:10px;color:#7f8c8d;margin-bottom:4px;max-height:28px;overflow:hidden">{subj}</div>'
            f'<span class="cat-badge" style="background:{CAT_CSS.get(cat,"#eee")};color:#fff">{cat.replace("_"," ").title()}</span>'
            f'<div style="font-size:16px;font-weight:bold;color:{clr};text-align:center;margin:6px 0">{suit}/10</div>'
            f'<div style="font-size:10px;color:#95a5a6;text-align:center">Q: {qs}</div>'
            f'</div></div>'
        )

    cards_html = "".join(card_html(i, r) for i, r in enumerate(all_images))
    total_cards = len(all_images)

    # Glance shows a small, stable sample; Grid shows every image.
    ranked = sorted(
        enumerate(all_images),
        key=lambda p: (p[1].get("_error", False), -(p[1].get("training_suitability") or 0), p[1]["image"]),
    )
    top_indices = [i for i, r in ranked if not r.get("_error")][:12]
    sample_html = "".join(card_html(i, all_images[i]) for i in top_indices)

    # ── list rows (details open in the modal; one row per image) ──
    list_rows = ""
    for i, r in enumerate(all_images):
        is_err = r.get("_error", False)
        cat = r.get("category", "unknown")
        suit = r.get("training_suitability", 0)
        lq = r.get("lora_quality", {})
        qs = f"{lq.get('linework','')}/{lq.get('contrast','')}/{lq.get('composition','')}/{lq.get('artifact_free','')}"
        subj = (r.get("subject") or "")[:80]
        notes = (r.get("error") or r.get("notes") or "")[:120]
        clr = _suit_color(suit)
        bg = "background:#fff5f5;" if is_err else ""
        list_rows += (
            f'<tr class="lrow" data-i="{i}" data-cat="{cat}" data-suit="{suit}" data-name="{r["image"]}" style="{bg}">'
            f'<td style="text-align:center;cursor:pointer" onclick="openDetail({i})" title="詳細を開く">{img_tag(r["image"], img_dir, "80px")}</td>'
            f'<td style="font-weight:bold;font-size:11px">{r["image"]}</td>'
            f'<td style="font-size:11px;color:#7f8c8d;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{subj}</td>'
            f'<td><span class="cat-badge" style="background:{CAT_CSS.get(cat,"#eee")};color:#fff">{cat.replace("_"," ").title()}</span></td>'
            f'<td style="font-weight:bold;color:{clr}">{suit}/10</td>'
            f'<td style="font-size:11px">{qs}</td>'
            f'<td style="font-size:10px;color:#95a5a6;max-width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{notes}</td>'
            f'</tr>'
        )

    # ── Grouped by category HTML ──
    grouped = OrderedDict()
    for i, r in enumerate(all_images):
        c = r.get("category", "unknown")
        grouped.setdefault(c, []).append((i, r))
    group_html = ""
    for cat, items in grouped.items():
        clr = CAT_CSS.get(cat, "#757575")
        group_html += (
            f'<div style="margin-bottom:20px">'
            f'<div style="background:{clr};color:#fff;padding:6px 12px;border-radius:6px;font-weight:600;font-size:13px">'
            f'{cat.replace("_", " ").title()} ({len(items)})</div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;padding:10px">'
        )
        for idx, r in items:
            suit = r.get("training_suitability", 0)
            subj = (r.get("subject") or "")[:60]
            sc = _suit_color(suit)
            group_html += (
                f'<div style="background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px;text-align:center;cursor:pointer" onclick="openDetail({idx})">'
                f'{img_tag(r["image"], img_dir, "100px")}'
                f'<div style="font-size:10px;font-weight:bold;margin-top:4px">{r["image"]}</div>'
                f'<div style="font-size:9px;color:#666;margin-top:2px">{subj}</div>'
                f'<div style="font-size:11px;color:{sc};font-weight:bold;margin-top:4px">{suit}/10</div>'
                f'</div>'
            )
        group_html += "</div></div>"

    figures = build_figures(stats, tag_labels, tag_values, tag_colors, vol_labels, vol_values)

    demo_link = (
        f'&nbsp;|&nbsp; <a href="{vlm_demo_url}" style="color:#fff;text-decoration:underline">📷 VLM Demo</a>'
        if vlm_demo_url else ""
    )

    extra_css = """
/* Tag view */
.tag-sec { margin-bottom: 20px; }
.tag-head { color: #fff; padding: 7px 12px; border-radius: 8px 8px 0 0; font-weight: 700; font-size: 13px; }
.tag-sec .gv { margin: 0; padding: 12px; background: #fff; border-radius: 0 0 12px 12px; box-shadow: 0 1px 6px rgba(0,0,0,.08); }

/* Detail modal */
.modal { position: fixed; inset: 0; background: rgba(15,20,40,.72); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 18px; }
.modal-card { background: #fff; border-radius: 14px; max-width: 1080px; width: 100%; max-height: 92vh; overflow: auto; box-shadow: 0 20px 60px rgba(0,0,0,.4); position: relative; }
.modal-close { position: sticky; top: 10px; float: right; margin: 10px 10px 0 0; z-index: 2; border: 1px solid #ddd; background: #fff; border-radius: 50%; width: 32px; height: 32px; font-size: 18px; line-height: 1; cursor: pointer; }
.modal-close:hover { background: #f0f2f5; }
.detail-grid { display: grid; grid-template-columns: minmax(240px, 400px) 1fr; gap: 22px; padding: 22px; }
.detail-img { width: 100%; border-radius: 10px; border: 1px solid #eee; background: #fafafa; }
.detail-file { font-size: 11px; color: #95a5a6; text-align: center; margin-top: 6px; word-break: break-all; }
.detail-subject { font-size: 17px; color: #1a237e; line-height: 1.4; margin-bottom: 10px; padding-right: 28px; }
.detail-badges { margin-bottom: 14px; }
.badge-tag { display: inline-block; padding: 2px 9px; border-radius: 999px; color: #fff; font-size: 11px; font-weight: 600; margin: 0 4px 4px 0; }
.badge-suit { display: inline-block; padding: 2px 9px; border-radius: 999px; color: #fff; font-size: 11px; font-weight: 700; margin: 0 4px 4px 0; }
.detail-block { margin-bottom: 14px; }
.detail-label { font-size: 11px; font-weight: 700; color: #95a5a6; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.detail-text { font-size: 13px; line-height: 1.65; color: #444; white-space: pre-wrap; }
.detail-text.err { color: #c62828; }
.qrow { display: grid; grid-template-columns: 110px 1fr 28px; gap: 8px; align-items: center; font-size: 12px; margin-bottom: 5px; color: #555; }
.qbar { height: 7px; background: #eef0f4; border-radius: 999px; overflow: hidden; }
.qbar i { display: block; height: 100%; background: linear-gradient(90deg,#3949ab,#5c6bc0); }
.detail-raw { margin-top: 6px; font-size: 12px; color: #666; }
.detail-raw summary { cursor: pointer; font-weight: 600; }
pre.raw { white-space: pre-wrap; word-break: break-word; background: #f7f8fa; border: 1px solid #eee; border-radius: 8px; padding: 10px; font-size: 11px; max-height: 240px; overflow: auto; margin-top: 8px; }
.modal-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding: 0 22px 22px; }
.btn { padding: 7px 14px; border: 1px solid #3949ab; background: #fff; color: #3949ab; border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 600; }
.btn:hover { background: #3949ab; color: #fff; }
.btn.rec { background: #3949ab; color: #fff; }
.btn.rec:hover { background: #283593; border-color: #283593; }
.seq-pos { font-size: 12px; color: #7f8c8d; margin-left: auto; }
@media (max-width: 800px) { .detail-grid { grid-template-columns: 1fr; } }
"""

    extra_js = """
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function catColor(t) { return CC[t] || '#607d8b'; }

let seqOrder = [], seqPos = -1, current = -1, speaking = false;

function visibleOrder() {
  return [...document.querySelectorAll('#grid .img-card')]
    .filter(e => e.style.display !== 'none')
    .map(e => parseInt(e.dataset.i, 10));
}

function qualityRows(q) {
  const keys = [['linework','Linework'], ['contrast','Contrast'], ['composition','Composition'], ['artifact_free','Artifact-free']];
  return keys.map(([k, label]) => {
    const v = q[k];
    const pct = Math.max(0, Math.min(100, (Number(v) || 0) * 10));
    return `<div class="qrow"><span>${label}</span><div class="qbar"><i style="width:${pct}%"></i></div><b>${v == null ? '-' : v}</b></div>`;
  }).join('');
}

function openDetail(i, keepOrder) {
  const d = DATA[i];
  if (!d) return;
  const modalEl = document.getElementById('detailModal');
  const bodyEl = document.getElementById('detailBody');
  if (!modalEl || !bodyEl) return;
  current = i;
  if (!keepOrder || seqOrder.indexOf(i) < 0) seqOrder = visibleOrder();
  seqPos = seqOrder.indexOf(i);
  if (seqPos < 0) { seqOrder = [i]; seqPos = 0; }
  stopSpeak();

  const q = d.quality || {};
  const tags = (d.tags || []).map(t => `<span class="badge-tag" style="background:${catColor(t)}">${esc(String(t).replace(/_/g, ' '))}</span>`).join('');
  const suitColor = d.suit >= 8 ? '#2e7d32' : d.suit >= 6 ? '#f57f17' : '#c62828';
  bodyEl.innerHTML = `
    <div class="detail-left">
      <img class="detail-img" src="${IMG}/${esc(d.image)}" alt="${esc(d.image)}" loading="eager">
      <div class="detail-file">${esc(d.image)}</div>
    </div>
    <div class="detail-right">
      <h2 class="detail-subject">${esc(d.subject || '(no subject)')}</h2>
      <div class="detail-badges">${tags}<span class="badge-suit" style="background:${suitColor}">Suitability ${d.suit}/10</span></div>
      ${d.style_notes ? `<div class="detail-block"><div class="detail-label">Style notes</div><div class="detail-text">${esc(d.style_notes)}</div></div>` : ''}
      <div class="detail-block"><div class="detail-label">Notes / comment</div><div class="detail-text${d.error ? ' err' : ''}">${esc(d.notes || '(none)')}</div></div>
      <div class="detail-block"><div class="detail-label">LoRA quality</div>${qualityRows(q)}</div>
      <details class="detail-raw"><summary>Raw VLM response</summary><pre class="raw" id="rawBox"></pre></details>
    </div>`;
  const raw = document.getElementById('rawBox');
  if (raw) raw.textContent = d.raw || '(no raw response)';
  const seqEl = document.getElementById('seqPos');
  if (seqEl) seqEl.textContent = `${seqPos + 1} / ${seqOrder.length}`;
  modalEl.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  updateSpeakBtn();
}

function closeDetail() {
  stopSpeak();
  const modalEl = document.getElementById('detailModal');
  if (modalEl) modalEl.classList.add('hidden');
  document.body.style.overflow = '';
}

function step(dir) {
  if (!seqOrder.length) return;
  seqPos = (seqPos + dir + seqOrder.length) % seqOrder.length;
  openDetail(seqOrder[seqPos], true);
}

function startSeq() {
  const order = visibleOrder();
  if (!order.length) return;
  seqOrder = order; seqPos = 0;
  openDetail(order[0], true);
}

function toggleSpeak() {
  if (!window.speechSynthesis) { alert('このブラウザは読み上げに対応していません'); return; }
  if (speaking) { stopSpeak(); return; }
  const d = DATA[current];
  if (!d) return;
  const parts = [];
  if (d.subject) parts.push(d.subject);
  if (d.style_notes) parts.push('スタイル。' + d.style_notes);
  if (d.notes) parts.push('注記。' + d.notes);
  if (d.tags && d.tags.length) parts.push('タグ。' + d.tags.join('、'));
  parts.push('学習適性。' + d.suit + '点。');
  const text = parts.join('。');
  const ja = /[\u3040-\u30ff\u3400-\u9fff]/.test(text);
  const u = new window.SpeechSynthesisUtterance(text);
  u.lang = ja ? 'ja-JP' : 'en-US';
  const v = window.speechSynthesis.getVoices().find(x => x.lang && x.lang.toLowerCase().startsWith(ja ? 'ja' : 'en'));
  if (v) u.voice = v;
  u.rate = 1.0;
  u.onend = () => { speaking = false; updateSpeakBtn(); };
  u.onerror = () => { speaking = false; updateSpeakBtn(); };
  speaking = true;
  updateSpeakBtn();
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

function stopSpeak() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  speaking = false;
  updateSpeakBtn();
}

function updateSpeakBtn() {
  const b = document.getElementById('speakBtn');
  if (b) b.textContent = speaking ? '⏹ 停止' : '🔊 読み上げ';
}

function tagCard(d, i) {
  const card = document.createElement('div'); card.className = 'img-card'; card.style.cursor = 'pointer';
  card.onclick = () => openDetail(i, true);
  const img = document.createElement('img');
  img.src = IMG + '/' + d.image; img.loading = 'lazy'; img.alt = d.image;
  img.style.cssText = 'width:100%;aspect-ratio:1;object-fit:cover;display:block';
  img.onerror = () => { img.style.background = '#ffebee'; img.alt = 'ERR'; img.removeAttribute('src'); };
  const box = document.createElement('div'); box.style.padding = '8px';
  const name = document.createElement('div'); name.textContent = d.image; name.style.cssText = 'font-weight:600;font-size:11px';
  const sub = document.createElement('div'); sub.textContent = (d.subject || '').slice(0, 70); sub.style.cssText = 'font-size:10px;color:#7f8c8d;margin:3px 0';
  const suit = document.createElement('div'); suit.textContent = d.suit + '/10';
  suit.style.cssText = 'font-size:12px;font-weight:700;color:' + (d.suit >= 8 ? '#2e7d32' : d.suit >= 6 ? '#f57f17' : '#c62828');
  box.append(name, sub, suit); card.append(img, box);
  return card;
}

function buildTags() {
  const root = document.getElementById('tagRoot');
  if (!root) return;
  const CAP = 12;
  const map = new Map();
  DATA.forEach((d, i) => (d.tags && d.tags.length ? d.tags : ['unknown']).forEach(t => {
    if (!map.has(t)) map.set(t, []);
    const arr = map.get(t);
    if (!arr.includes(i)) arr.push(i);
  }));
  const frag = document.createDocumentFragment();
  [...map.entries()].sort((a, b) => b[1].length - a[1].length).forEach(([tag, ids]) => {
    const sec = document.createElement('div'); sec.className = 'tag-sec';
    const head = document.createElement('div'); head.className = 'tag-head'; head.style.background = catColor(tag);
    head.textContent = tag.replace(/_/g, ' ') + ' (' + ids.length + ')';
    const grid = document.createElement('div'); grid.className = 'gv';
    ids.slice(0, CAP).forEach(i => grid.appendChild(tagCard(DATA[i], i)));
    sec.append(head, grid);
    if (ids.length > CAP) {
      const more = document.createElement('button');
      more.className = 'btn';
      more.style.margin = '12px';
      more.textContent = 'さらに表示（残り ' + (ids.length - CAP) + ' 件）';
      more.onclick = () => {
        ids.slice(CAP).forEach(i => grid.appendChild(tagCard(DATA[i], i)));
        more.remove();
      };
      sec.append(more);
    }
    frag.appendChild(sec);
  });
  root.replaceChildren(frag);
}

document.addEventListener('keydown', e => {
  const modalEl = document.getElementById('detailModal');
  if (!modalEl || modalEl.classList.contains('hidden')) return;
  if (e.key === 'Escape') closeDetail();
  else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
});
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="{plotly_js}" charset="utf-8"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; }}

/* Header */
.header {{
    background: linear-gradient(135deg, #1a237e 0%, #3949ab 50%, #5c6bc0 100%);
    color: #fff; padding: 24px 20px; text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,.15);
}}
.header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -.5px; }}
.header .meta {{ font-size: 12px; opacity: .85; margin-top: 4px; }}

/* Container */
.c {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}

/* Stat cards */
.sgrid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
.sc {{ background: #fff; border-radius: 12px; padding: 16px; text-align: center; box-shadow: 0 1px 6px rgba(0,0,0,.08); }}
.sc .lbl {{ font-size: 11px; color: #95a5a6; text-transform: uppercase; letter-spacing: .5px; }}
.sc .val {{ font-size: 26px; font-weight: 700; color: #1a237e; margin: 4px 0; }}
.sc .sub {{ font-size: 11px; color: #7f8c8d; }}
.sc.err .val {{ color: #c62828; }}

/* Charts */
.cgrid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 20px; }}
.cc {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 6px rgba(0,0,0,.08); }}
.cc h3 {{ font-size: 14px; color: #1a237e; margin-bottom: 10px; }}

/* Controls */
.ctrls {{ background: #fff; border-radius: 12px; padding: 12px 16px; box-shadow: 0 1px 6px rgba(0,0,0,.08); margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.ctrls label {{ font-size: 11px; font-weight: 600; color: #666; text-transform: uppercase; }}
.ctrls select, .ctrls input {{ padding: 5px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 12px; background: #fafafa; }}
.ctrls button {{ padding: 5px 14px; border: 1px solid #3949ab; background: #fff; color: #3949ab; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: all .15s; }}
.ctrls button:hover {{ background: #3949ab; color: #fff; }}
.ctrls button.on {{ background: #3949ab; color: #fff; }}
.vtog {{ margin-left: auto; display: flex; gap: 4px; }}

.info {{ font-size: 12px; color: #999; margin-bottom: 12px; }}

/* Glance */
.glance {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 6px rgba(0,0,0,.08); margin-bottom: 20px; }}
.glance h3 {{ margin-top: 0; }}

/* Group */
.grp {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 6px rgba(0,0,0,.08); margin-bottom: 20px; }}

/* Graph */
.graph {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 6px rgba(0,0,0,.08); margin-bottom: 20px; }}

/* Grid view */
.gv {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 14px; margin-bottom: 20px; }}
.img-card {{ background: #fff; border-radius: 10px; box-shadow: 0 1px 6px rgba(0,0,0,.08); overflow: hidden; transition: transform .2s; }}
.img-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.12); }}

/* List */
.lv, .tv {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 6px rgba(0,0,0,.08); overflow: hidden; margin-bottom: 20px; }}
.lv table, .tv table {{ width: 100%; border-collapse: collapse; }}
.lv th, .tv th {{ background: #1a237e; color: #fff; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; position: sticky; top: 0; }}
.lv td, .tv td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 12px; }}
.lv tr:hover, .tv tr:hover {{ background: #f5f7ff; }}

.hidden {{ display: none !important; }}
.cat-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; text-transform: uppercase; }}

@media (max-width: 768px) {{
    .cgrid {{ grid-template-columns: 1fr; }}
    .gv {{ grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }}
    .ctrls {{ flex-direction: column; align-items: stretch; }}
    .vtog {{ margin-left: 0; justify-content: center; }}
}}
{extra_css}
</style>
</head>
<body>

<div class="header">
    <h1>🎨 Hokusai Manga — VLM Review Dashboard</h1>
    <div class="meta">
        Generated: {datetime.now():%Y-%m-%d %H:%M:%S}
        &nbsp;|&nbsp; {stats["total"]} images
        &nbsp;|&nbsp; Avg Suitability: {stats["avg_suitability"]}/10
        {demo_link}
    </div>
</div>

<div class="c">

    <!-- GLANCE View: Summary + stats + sample cards -->
    <div class="glance" id="glance">
        <h3 style="color:#1a237e;margin-bottom:12px">📊 Dataset Overview</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:20px">
            <div class="sc"><div class="lbl">Total Images</div><div class="val">{stats["total"]}</div><div class="sub">annotated images</div></div>
            <div class="sc"><div class="lbl">Avg Suitability</div><div class="val">{stats["avg_suitability"]}</div><div class="sub">/10 ({stats["median_suitability"]} median)</div></div>
            <div class="sc"><div class="lbl">Categories</div><div class="val">{len(stats["categories"])}</div><div class="sub">distinct types</div></div>
            <div class="sc"><div class="lbl">Volumes</div><div class="val">{len(vol_counts)}</div><div class="sub">detected from filenames</div></div>
            <div class="sc"><div class="lbl">Tags</div><div class="val">{len(tag_counts)}</div><div class="sub">category tokens</div></div>
            <div class="sc"><div class="lbl">Linework</div><div class="val">{stats["quality"].get("linework",0):.1f}</div><div class="sub">/10 avg quality</div></div>
            <div class="sc err"><div class="lbl">Errors</div><div class="val">{err_count}</div><div class="sub">{err_pct}% timeout/unparseable</div></div>
        </div>
        <h3 style="color:#1a237e;margin:0 0 10px">⭐ Top rated samples</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px">
            {sample_html}
        </div>
    </div>

    <!-- Controls -->
    <div class="ctrls">
        <label>VIEW</label>
        <div class="vtog">
            <button id="bGlance" class="on" onclick="setView('glance')">👁 Glance</button>
            <button id="bGrid" onclick="setView('grid')">☷ Grid</button>
            <button id="bList" onclick="setView('list')">☰ List</button>
            <button id="bGroup" onclick="setView('group')">📁 Group</button>
            <button id="bGraph" onclick="setView('graph')">📈 Graph</button>
            <button id="bTags" onclick="setView('tags')">🏷 Tags</button>
        </div>
        <label style="margin-left:16px">Sort</label>
        <select id="selSort" onchange="apply()">
            <option value="sD">Suitability ↓</option>
            <option value="sA">Suitability ↑</option>
            <option value="nA">Name A→Z</option>
            <option value="nZ">Name Z→A</option>
            <option value="c">Category</option>
        </select>
        <label>Category</label>
        <select id="selCat" onchange="apply()"><option value="">All</option>{cat_opts}</select>
        <label>Suitability</label>
        <select id="selSuit" onchange="apply()">
            <option value="">All</option>
            <option value="9-10">9-10 Excellent</option>
            <option value="8-8">8 Good</option>
            <option value="7-7">7 Average</option>
            <option value="6-6">6 Fair</option>
            <option value="4-5">4-5 Poor</option>
            <option value="0-3">0-3 Errors</option>
        </select>
        <button onclick="reset()">Reset</button>
        <button onclick="errorsOnly()">Errors Only</button>
        <button onclick="startSeq()">▶ 順番に見る</button>
    </div>

    <div class="info" id="info">Showing {total_cards} / {total_cards}</div>

    <!-- Grid -->
    <div class="gv hidden" id="grid">{cards_html}</div>

    <!-- List -->
    <div class="lv hidden" id="list">
        <table>
            <colgroup>
                <col style="width:96px"><col style="width:172px"><col style="width:340px">
                <col style="width:112px"><col style="width:96px"><col style="width:88px"><col>
            </colgroup>
            <thead><tr><th></th><th>Image</th><th>Subject</th><th>Category</th><th>Suitability</th><th>Quality</th><th>Notes</th></tr></thead>
            <tbody>{list_rows}</tbody>
        </table>
    </div>

    <!-- Grouped by Category -->
    <div class="grp hidden" id="group">{group_html}</div>

    <!-- Grouped by Tags (rebuilt from category tokens) -->
    <div class="grp hidden" id="tags"><div id="tagRoot"></div></div>

    <!-- Graph / Charts Focus -->
    <div class="graph hidden" id="graph">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;margin-bottom:20px">
            <div class="cc"><h3>🍩 Category Distribution</h3>{figures["cat"]}</div>
            <div class="cc"><h3>📊 Suitability Histogram</h3>{figures["suit"]}</div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px">
            <div class="cc"><h3>🎯 LoRA Quality Radar</h3>{figures["qual"]}</div>
            <div class="cc"><h3>🥧 Suitability Ranges</h3>{figures["dist"]}</div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;margin-top:20px">
            <div class="cc"><h3>📚 Volume Distribution</h3>{figures["vol"]}</div>
            <div class="cc"><h3>🏷 Tag Distribution</h3>{figures["tag"]}</div>
        </div>
    </div>


    <!-- Detail modal: image / comments / TTS / sequential navigation -->
    <div class="modal hidden" id="detailModal" onclick="if(event.target===this)closeDetail()">
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="Image detail">
            <button class="modal-close" onclick="closeDetail()" aria-label="Close">×</button>
            <div class="detail-grid" id="detailBody"></div>
            <div class="modal-actions">
                <button class="btn" onclick="step(-1)">← 前</button>
                <button class="btn" onclick="step(1)">次 →</button>
                <button class="btn rec" id="speakBtn" onclick="toggleSpeak()">🔊 読み上げ</button>
                <span class="seq-pos" id="seqPos"></span>
            </div>
        </div>
    </div>

</div>

<script>
const DATA = {detail_json};
const IMG = {img_json};
const CC = {cat_json};

buildTags();
apply();

// ── View toggle ──
function setView(v) {{
    const views = ['glance','grid','list','group','graph','tags'];
    views.forEach(n => document.getElementById(n).classList.add('hidden'));
    document.getElementById(v).classList.remove('hidden');
    document.querySelectorAll('.vtog button').forEach(b=>b.classList.remove('on'));
    const idMap = {{glance:'bGlance',grid:'bGrid',list:'bList',group:'bGroup',graph:'bGraph',tags:'bTags'}};
    if(idMap[v]) document.getElementById(idMap[v]).classList.add('on');
    if(v === 'graph') {{
        setTimeout(() => ['chCat','chSuit','chQual','chDist','chVol','chTag'].forEach(id => {{
            const el = document.getElementById(id);
            if(el) Plotly.Plots.resize(el);
        }}), 60);
    }}
    apply();
    const info = document.getElementById('info');
    if(v === 'glance') info.textContent = 'Overview';
    else if(v === 'group') info.textContent = document.querySelectorAll('#group > div').length + ' groups';
    else if(v === 'tags') info.textContent = document.querySelectorAll('#tagRoot .tag-sec').length + ' tags';
    else if(v === 'graph') info.textContent = '6 charts';
}}

// ── Filter / Sort ──
function apply() {{
    const sort = document.getElementById('selSort').value;
    const catF = document.getElementById('selCat').value;
    const suitF = document.getElementById('selSuit').value;

    const cards = [...document.querySelectorAll('#grid .img-card')];
    const rows = [...document.querySelectorAll('#list .lrow')];

    // Filter
    const pick = (el) => {{
        const cat = el.dataset.cat, suit = parseInt(el.dataset.suit);
        if(catF && cat !== catF) return false;
        if(suitF) {{
            const [lo,hi] = suitF.split('-').map(Number);
            if(suit < lo || suit > hi) return false;
        }}
        return true;
    }};

    const show = (els) => els.forEach(e => e.style.display = pick(e) ? '' : 'none');
    show(cards);
    show(rows);

    // Sort all elements (visible + hidden) so filters can be cleared safely
    const doSort = (els) => {{
        const sorted = [...els].sort((a, b) => {{
            switch(sort) {{
                case 'sD': return parseInt(b.dataset.suit) - parseInt(a.dataset.suit);
                case 'sA': return parseInt(a.dataset.suit) - parseInt(b.dataset.suit);
                case 'nA': return a.dataset.name.localeCompare(b.dataset.name);
                case 'nZ': return b.dataset.name.localeCompare(a.dataset.name);
                case 'c':  return a.dataset.cat.localeCompare(b.dataset.cat);
                default: return 0;
            }}
        }});
        const parent = els[0]?.parentNode;
        if(!parent) return;
        sorted.forEach(e => parent.appendChild(e));
    }};

    doSort(cards);
    doSort(rows);

    document.getElementById('info').textContent =
        `Showing ${{cards.filter(e=>e.style.display!=='none').length}} / ${{cards.length}}`;
}}

function reset() {{
    document.getElementById('selSort').value = 'sD';
    document.getElementById('selCat').value = '';
    document.getElementById('selSuit').value = '';
    setView('glance');
}}

function errorsOnly() {{
    document.getElementById('selCat').value = 'error';
    document.getElementById('selSuit').value = '';
    setView('grid');
}}

{extra_js}
</script>

</body>
</html>"""

    if output is not None:
        output.write_text(html, encoding="utf-8")
        print(f"Dashboard → {output}")
    return html


# ── Entry point ────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Hokusai VLM Dashboard")
    ap.add_argument("--jsonl", type=Path)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--img-dir", default="images", help="Image path prefix written into the HTML (relative to the output file)")
    ap.add_argument("--title", default="Hokusai Dashboard")
    args = ap.parse_args()

    sd = Path(__file__).resolve().parent
    repo_root = sd.parents[2]
    docs_dir = repo_root / "docs"
    dd = docs_dir / "data"

    jf = args.jsonl or dd / "hokusai_vlm_reviews.jsonl"
    df = args.db or dd / "hokusai_vlm_reviews.db"

    all_images, errors = load_all_images(jf, df)
    print(f"Reviews: {len(all_images) - len(errors)}")
    print(f"Errors:  {len(errors)}")

    output = args.output or (docs_dir / "dashboard.html")
    build_dashboard(all_images, errors, args.img_dir, output, args.title)


if __name__ == "__main__":
    main()