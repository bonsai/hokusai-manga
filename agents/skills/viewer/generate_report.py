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
    err = (
        '<div style=&quot;width:' + size + ';height:' + size +
        ';background:#ffebee;display:flex;align-items:center;'
        'justify-content:center;color:#c62828;font-size:10px&quot;>ERR</div>'
    )
    return (
        f'<img src="{src}" style="width:{size};height:{size};object-fit:cover;'
        f'border-radius:6px;border:1px solid #ddd;" loading="lazy" '
        f"onerror=\\\"this.outerHTML='{err}'\\\">"
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


# ── Dashboard builder ──────────────────────────────────────────────────

def build_dashboard(
    all_images: list[dict],
    errors: list[dict],
    img_dir: str,
    output: Path,
    title: str = "Hokusai Dashboard",
) -> None:
    total = len(all_images)
    err_count = len(errors)
    err_pct = round(err_count / total * 100, 1) if total else 0

    stats = compute_stats([i for i in all_images if not i.get("_error")])

    # ── category options ──
    cat_opts = "".join(
        f'<option value="{c}">{c.replace("_", " ").title()}</option>'
        for c in sorted(stats["categories"])
    )

    # ── grid cards ──
    cards_html = ""
    for i, r in enumerate(all_images):
        is_err = r.get("_error", False)
        cat = r.get("category", "unknown")
        suit = r.get("training_suitability", 0)
        lq = r.get("lora_quality", {})
        qs = f"{lq.get('linework','')}/{lq.get('contrast','')}/{lq.get('composition','')}/{lq.get('artifact_free','')}"
        subj = (r.get("subject") or "")[:80]
        clr = _suit_color(suit)
        border = 'border:2px solid #e74c3c' if is_err else ""
        cards_html += (
            f'<div class="img-card" data-i="{i}" data-cat="{cat}" data-suit="{suit}" data-name="{r["image"]}" style="{border}">'
            f'<div style="text-align:center;padding:8px">{img_tag(r["image"], img_dir, "150px")}</div>'
            f'<div style="padding:0 10px 10px">'
            f'<div style="font-weight:bold;font-size:11px;margin-bottom:4px">{r["image"]}</div>'
            f'<div style="font-size:10px;color:#7f8c8d;margin-bottom:4px;max-height:28px;overflow:hidden">{subj}</div>'
            f'<span class="cat-badge" style="background:{CAT_CSS.get(cat,"#eee")};color:{clr}">{cat.replace("_"," ").title()}</span>'
            f'<div style="font-size:16px;font-weight:bold;color:{clr};text-align:center;margin:6px 0">{suit}/10</div>'
            f'<div style="font-size:10px;color:#95a5a6;text-align:center">Q: {qs}</div>'
            f'</div></div>'
        )

    # ── list rows ──
    list_rows = ""
    toggle_rows = ""
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

        row = (
            f'<tr class="lrow" data-i="{i}" data-cat="{cat}" data-suit="{suit}" data-name="{r["image"]}" style="{bg}">'
            f'<td style="text-align:center;cursor:pointer" onclick="togDetail(this)">▶</td>'
            f'<td style="font-weight:bold;font-size:11px">{r["image"]}</td>'
            f'<td style="font-size:11px;color:#7f8c8d;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{subj}</td>'
            f'<td><span class="cat-badge" style="background:{CAT_CSS.get(cat,"#eee")};color:{clr}">{cat.replace("_"," ").title()}</span></td>'
            f'<td style="font-weight:bold;color:{clr}">{suit}/10</td>'
            f'<td style="font-size:11px">{qs}</td>'
            f'<td style="font-size:10px;color:#95a5a6;max-width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{notes}</td>'
            f'</tr>'
            f'<tr class="detail-row" style="display:none;background:#f8f9fa"><td colspan="7" style="padding:10px">'
            f'<table style="width:100%;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden">'
            f'<tr><td style="padding:6px;font-weight:bold;border-bottom:1px solid #e0e0e0">Subject</td><td style="padding:6px;border-bottom:1px solid #e0e0e0">{subj}</td></tr>'
            f'<tr><td style="padding:6px;font-weight:bold;border-bottom:1px solid #e0e0e0">Notes</td><td style="padding:6px;border-bottom:1px solid #e0e0e0">{notes}</td></tr>'
            f'<tr><td style="padding:6px;font-weight:bold;border-bottom:1px solid #e0e0e0">Category</td><td style="padding:6px;border-bottom:1px solid #e0e0e0">{cat}</td></tr>'
            f'<tr><td style="padding:6px;font-weight:bold;border-bottom:1px solid #e0e0e0">Suitability</td><td style="padding:6px;border-bottom:1px solid #e0e0e0">{suit}/10</td></tr>'
            f'<tr><td style="padding:6px;font-weight:bold">LoRA Quality</td><td style="padding:6px">{qs} (L/C/C/A)</td></tr>'
            f'</table></td></tr>'
        )
        toggle_rows += row

        list_rows += (
            f'<tr class="lrow" data-i="{i}" data-cat="{cat}" data-suit="{suit}" data-name="{r["image"]}" style="{bg}">'
            f'<td style="text-align:center">{img_tag(r["image"], img_dir, "80px")}</td>'
            f'<td style="font-weight:bold;font-size:11px">{r["image"]}</td>'
            f'<td style="font-size:11px;color:#7f8c8d;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{subj}</td>'
            f'<td><span class="cat-badge" style="background:{CAT_CSS.get(cat,"#eee")};color:{clr}">{cat.replace("_"," ").title()}</span></td>'
            f'<td style="font-weight:bold;color:{clr}">{suit}/10</td>'
            f'<td style="font-size:11px">{qs}</td>'
            f'<td style="font-size:10px;color:#95a5a6;max-width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{notes}</td>'
            f'</tr>'
        )

    # error cards
    err_html = ""
    if err_count:
        for e in errors:
            err_html += (
                f'<div style="background:#fff3e0;border-radius:8px;padding:10px;text-align:center">'
                f'{img_tag(e["image"], img_dir, "120px")}'
                f'<div style="font-weight:bold;font-size:12px;margin:5px 0;color:#c62828">{e["image"]}</div>'
                f'<div style="font-size:11px;color:#795548">{e.get("error") or ""[:150]}</div></div>'
            )

    # ── Grouped by category HTML ──
    grouped = OrderedDict()
    for r in all_images:
        c = r.get("category", "unknown")
        grouped.setdefault(c, []).append(r)
    group_html = ""
    for cat, items in grouped.items():
        clr = CAT_CSS.get(cat, "#757575")
        group_html += (
            f'<div style="margin-bottom:20px">'
            f'<div style="background:{clr};color:#fff;padding:6px 12px;border-radius:6px;font-weight:600;font-size:13px">'
            f'{cat.replace("_", " ").title()} ({len(items)})</div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;padding:10px">'
        )
        for r in items:
            suit = r.get("training_suitability", 0)
            subj = (r.get("subject") or "")[:60]
            sc = _suit_color(suit)
            group_html += (
                f'<div style="background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px;text-align:center">'
                f'{img_tag(r["image"], img_dir, "100px")}'
                f'<div style="font-size:10px;font-weight:bold;margin-top:4px">{r["image"]}</div>'
                f'<div style="font-size:9px;color:#666;margin-top:2px">{subj}</div>'
                f'<div style="font-size:11px;color:{sc};font-weight:bold;margin-top:4px">{suit}/10</div>'
                f'</div>'
            )
        group_html += "</div></div>"

    # ── plotly chart data ──
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

    plotly_data = json.dumps({
        "cat_labels": cat_labels,
        "cat_values": cat_values,
        "cat_colors": cat_colors,
        "suit_labels": suit_labels,
        "suit_values": suit_values,
        "suit_colors": suit_colors,
        "qual_labels": qual_labels,
        "qual_values": qual_values,
        "dist_labels": dist_labels,
        "dist_values": dist_values,
        "dist_colors": dist_colors,
    })

    plotly_layout = json.dumps({
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Inter,sans-serif", "size": 12, "color": "#555"},
        "margin": {"t": 10, "b": 30, "l": 40, "r": 20},
    })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js" charset="utf-8"></script>
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
</style>
</head>
<body>

<div class="header">
    <h1>🎨 Hokusai Manga — VLM Review Dashboard</h1>
    <div class="meta">
        Generated: {datetime.now():%Y-%m-%d %H:%M:%S}
        &nbsp;|&nbsp; {stats["total"]} images
        &nbsp;|&nbsp; Avg Suitability: {stats["avg_suitability"]}/10
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
            <div class="sc"><div class="lbl">Linework</div><div class="val">{stats["quality"].get("linework",0):.1f}</div><div class="sub">/10 avg quality</div></div>
            <div class="sc err"><div class="lbl">Errors</div><div class="val">{err_count}</div><div class="sub">{err_pct}% timeout/unparseable</div></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px">
            {cards_html}
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
    </div>

    <div class="info" id="info">Showing 0 / {stats["total"]}</div>

    <!-- Grid -->
    <div class="gv hidden" id="gv">{cards_html}</div>

    <!-- List -->
    <div class="lv hidden" id="lv">
        <table>
            <thead><tr><th></th><th>Image</th><th>Subject</th><th>Category</th><th>Suitability</th><th>Quality</th><th>Notes</th></tr></thead>
            <tbody>{list_rows}</tbody>
        </table>
    </div>

    <!-- Grouped by Category -->
    <div class="grp hidden" id="grp">{group_html}</div>

    <!-- Graph / Charts Focus -->
    <div class="graph hidden" id="graph">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;margin-bottom:20px">
            <div class="cc"><h3>🍩 Category Distribution</h3><div id="chCat" style="height:400px"></div></div>
            <div class="cc"><h3>📊 Suitability Histogram</h3><div id="chSuit" style="height:400px"></div></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px">
            <div class="cc"><h3>🎯 LoRA Quality Radar</h3><div id="chQual" style="height:400px"></div></div>
            <div class="cc"><h3>🥧 Suitability Ranges</h3><div id="chDist" style="height:400px"></div></div>
        </div>
    </div>

    <!-- Toggle Detail (for List view) -->
    <div class="tv hidden" id="tv">
        <table>
            <thead><tr><th></th><th>Image</th><th>Subject</th><th>Category</th><th>Suitability</th><th>Quality</th><th>Notes</th></tr></thead>
            <tbody>{toggle_rows}</tbody>
        </table>
    </div>

    <!-- Errors -->
    {err_html}

</div>

<script>
const D = {plotly_data};
const L = {plotly_layout};

Plotly.newPlot('chCat', [{{type:'pie', labels:D.cat_labels, values:D.cat_values, hole:.5, marker:{{colors:D.cat_colors}}}}], Object.assign({{showlegend:true, legend:{{font:{{size:11}}}}}}, L));

Plotly.newPlot('chSuit', [{{type:'bar', x:D.suit_labels, y:D.suit_values, marker:{{color:D.suit_colors}}, text:D.suit_values, textposition:'auto', textfont:{{size:11}}}}], Object.assign({{yaxis:{{title:'Count', range:[0,'auto']}}}}, L));

Plotly.newPlot('chQual', [{{type:'radar', labels:D.qual_labels, values:D.qual_values, fill:'toself', fillcolor:'rgba(57,73,171,.15)', line:{{color:'#3949ab'}}}}], Object.assign({{radar:{{range:[0,10]}}, polar:{{angularaxis:{{tickfont:{{size:11}}}}}}}}, L));

Plotly.newPlot('chDist', [{{type:'pie', labels:D.dist_labels, values:D.dist_values, hole:.45, marker:{{colors:D.dist_colors}}}}], Object.assign({{showlegend:true, legend:{{font:{{size:11}}}}}}, L));

// ── View toggle ──
function setView(v) {{
    const views = ['glance','grid','list','group','graph','tv'];
    views.forEach(n => document.getElementById(n).classList.add('hidden'));
    document.getElementById(v).classList.remove('hidden');
    document.querySelectorAll('.vtog button').forEach(b=>b.classList.remove('on'));
    const idMap = {{glance:'bGlance',grid:'bGrid',list:'bList',group:'bGroup',graph:'bGraph'}};
    if(idMap[v]) document.getElementById(idMap[v]).classList.add('on');
    apply();
}}

function togDetail(el) {{
    const row = el.closest('tr');
    const det = row.nextElementSibling;
    if(det && det.classList.contains('detail-row')) {{
        det.style.display = det.style.display==='none' ? 'table-row' : 'none';
        el.textContent = det.style.display==='none' ? '▶' : '▼';
    }}
}}

// ── Filter / Sort ──
function apply() {{
    const sort = document.getElementById('selSort').value;
    const catF = document.getElementById('selCat').value;
    const suitF = document.getElementById('selSuit').value;

    const cards = [...document.querySelectorAll('.img-card')];
    const rows = [...document.querySelectorAll('.lrow')];

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

    // Sort — collect visible then re-append
    const doSort = (els) => {{
        const vis = els.filter(e => e.style.display !== 'none');
        vis.sort((a, b) => {{
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
        vis.forEach(e => parent.appendChild(e));
        document.querySelectorAll('.detail-row').forEach(dr => dr.style.display = 'none');
        document.querySelectorAll('.lrow').forEach(lr => {{ const nxt = lr.nextElementSibling; if(nxt?.classList?.contains('detail-row')) nxt.style.display='none'; }});
        document.querySelectorAll('.lrow').forEach(lr => lr.querySelector('td') && (lr.querySelector('td').textContent='▶'));
    }};

    doSort(cards);
    doSort(rows);

    document.getElementById('info').textContent =
        `$Showing ${{cards.filter(e=>e.style.display!=='none').length}} / ${{stats["total"]}}`;
}}

function reset() {{
    document.getElementById('selSort').value = 'sD';
    document.getElementById('selCat').value = '';
    document.getElementById('selSuit').value = '';
    setView('glance');
}}

function errorsOnly() {{
    document.getElementById('selSuit').value = '0-3';
    apply();
}}
</script>

</body>
</html>"""

    output.write_text(html, encoding="utf-8")
    print(f"Dashboard → {output}")


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

    reviews = load_reviews(jf, df)
    print(f"Reviews: {len(reviews)}")
    errors = load_errors(df) if df.exists() else []
    print(f"Errors:  {len(errors)}")

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

    output = args.output or (docs_dir / "dashboard.html")
    img_dir = args.img_dir
    build_dashboard(all_images, errors, img_dir, output, args.title)


if __name__ == "__main__":
    main()