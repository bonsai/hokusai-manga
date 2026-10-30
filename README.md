# Hokusai Manga — NDL IIIF / LoRA dataset

NDL IIIF-based research tools for preparing publicly accessible pages of Katsushika Hokusai's *Hokusai Manga* as a compact LoRA training dataset, plus VLM annotation and a static review dashboard.

## Repository layout

```
.
├── README.md                 # 唯一の構造・使い方ドキュメント
├── requirements.txt          # fastapi / uvicorn / plotly
├── docs/                     # GitHub Pages 配信ルート（生成物 + 公開データ）
│   ├── index.html            # ランディングページ
│   ├── dashboard.html        # VLM レビュー集計（viewer skill が生成）
│   ├── viewer.html           # 巻メタデータビューア
│   ├── recap.html            # 直近セッションの作業サマリ（RECAP.md は Markdown 版）
│   ├── plotly.min.js         # 同梱 plotly.js（ダッシュボードが相対参照）
│   ├── demo/                 # デモ用スクリーンショット（index.html から掲載）
│   ├── images/               # 114枚のページ画像（720px幅）
│   ├── img/index.json        # viewer 用画像インデックス（packager skill が生成）
│   └── data/                 # 公開データ（metadata / annotations / VLM 注釈）
├── agents/skills/            # スキーマ（skill.yaml）+ worker（*.py）のみ
│   ├── getter/               # NDL IIIF から画像取得
│   ├── packager/             # LoRA ZIP 作成・画像インデックス生成
│   ├── reviewer/             # VLM 注釈（docs/data を更新）
│   └── viewer/               # docs/dashboard.html 生成 + FastAPI サーバ
└── .github/workflows/        # 1巻ずつDL / 一括DL / 結合パッケージ / GitHub Pages
```

### Rules

- `agents/` には **スキーマ (`skill.yaml`) と worker (`*.py`) だけ**を置く。HTML・データ・出力は置かない。
- `docs/` は **GitHub Pages の配信物と公開データの置き場**。成果物はここにだけ書く。
- 生成物は生成元の worker が `docs/` 配下へ出力する（手動コピーしない）。
- 一時ファイル・外部由来の大容量データは `assets/`, `dist/`, `local/`（すべて git 管理外）。
- ディレクトリ構造の記述はこの README だけに置く。
> **Workflow policy:** download and verify one volume at a time. Do not treat a partial download as complete. Combine the volumes only after reviewing the per-volume artifacts.

## Volume-by-volume workflow

The preferred path is **one volume at a time**: download a single PID, inspect its artifact, then move on. Never treat a partial download as complete, and combine volumes only after copying the Kanban below.

1. Open [Actions → Download one Hokusai Manga volume](https://github.com/bonsai/hokusai-manga/actions/workflows/download-one-volume.yml).
2. Select **Run workflow** and choose exactly one PID (`851646`–`851660`).
3. Check the run summary for `Pages available: N/M`, then download the `hokusai-manga-volume-<PID>` artifact.
4. Inspect `pages.json` and `errors.txt`. Missing pages mean the volume is **partial**, not done.
5. Move that volume's checkbox in the Kanban below, then repeat for the next PID.

The bulk [Download Hokusai Manga Volumes](https://github.com/bonsai/hokusai-manga/actions/workflows/download-volumes.yml) workflow (`roll: all`) still exists for convenience; it runs the same downloader through `agents/skills/getter/download_rolls.py`.

## Kanban

Update this board as each volume is processed. The volume is **Done** only when its artifact has been inspected and its missing-page status is understood.

### To do

- [ ] **Volume 1 — PID 851646**
- [ ] **Volume 3 — PID 851648**
- [ ] **Volume 4 — PID 851649**
- [ ] **Volume 5 — PID 851650**
- [ ] **Volume 6 — PID 851651**
- [ ] **Volume 7 — PID 851652**
- [ ] **Volume 8 — PID 851653**
- [ ] **Volume 9 — PID 851654**
- [ ] **Volume 10 — PID 851655**
- [ ] **Volume 11 — PID 851656**
- [ ] **Volume 12 — PID 851657**
- [ ] **Volume 13 — PID 851658**
- [ ] **Volume 14 — PID 851659**
- [ ] **Volume 15 — PID 851660**

### Doing

- [ ] **Volume 2 — PID 851647** — run the one-volume action and inspect its artifact.

### Done

- [ ] No volumes verified yet.

### How a Kanban entry is produced

- artifact `hokusai-manga-volume-<PID>` contains `assets/<PID>/` and `docs/data/metadata.json`
- `pages.json` records per-page `download_status` (`downloaded` / `available` / `error`)
- a volume moves to **Done** only when every page is accounted for and its `errors.txt` is understood

## Combine collected volumes into the LoRA ZIP

1. Open [Actions → Combine collected volumes for LoRA](https://github.com/bonsai/hokusai-manga/actions/workflows/package-collected-volumes.yml).
2. Enter the comma-separated run IDs of the completed volume downloads in `run_ids`.
3. Download the `hokusai-manga-lora-dataset-combined` artifact and inspect the ZIP before training.

## Agents (skills)

| Skill | Schema | Workers | Writes |
|-------|--------|---------|--------|
| `getter` | `agents/skills/getter/skill.yaml` | `download_rolls.py`, `download_ndl_iiif.py` | `assets/<pid>/`, `docs/data/metadata.json` |
| `packager` | `agents/skills/packager/skill.yaml` | `package_lora_dataset.py`, `build_img_index.py` | `dist/`, `docs/img/index.json` |
| `reviewer` | `agents/skills/reviewer/skill.yaml` | `vlm_reviewer.py`, `hokusai_reviewer.py`, `batch_review.py`, `review_10_batch*.py` | `docs/data/hokusai_vlm_reviews.{jsonl,db}` |
| `viewer` | `agents/skills/viewer/skill.yaml` | `server.py`, `generate_report.py` | `docs/dashboard.html`, HTTP API |

All workers resolve paths from the repository root, so they can be run from any directory.

## Data

- Public data and VLM annotations: `docs/data/` (see [`docs/data/README.md`](docs/data/README.md))
- Page images: `docs/images/`
- Downloaded originals (gitignored): `assets/`

## Dashboard features

`docs/dashboard.html` is a fully static export, and `agents/skills/viewer/server.py` serves the same UI through FastAPI. All charts are built with **plotly.py** (`plotly.graph_objects`), not hand-written chart JS.

- **Glance** — KPI cards (images, suitability, categories, volumes, tags, errors) + sample cards
- **Grid / List / Group** — browse by card, table, or category
- **Tags** — rebuilt groups from multi-label category tokens (an image can appear under several tags)
- **Graph** — category, suitability, LoRA quality radar, suitability ranges, volume distribution, tag distribution
- **Network** — tag co-occurrence SVG (embedded at build time; downloadable)
- **Detail** — click any card or list thumbnail to open full comments (subject, style notes, notes, quality bars, raw VLM response)
- **Search** — one box filters image name / subject / notes across Grid, List and Group; press `/` to focus it
- **読み上げ** — speak the current detail via the Web Speech API (ja-JP / en-US auto); **Space** toggles speak/stop
- **順番に見る** — sequential viewer over the current filter/sort; ← / → move, Space toggles 読み上げ, Esc closes

### Screenshots

`docs/index.html` shows three demo captures, generated headlessly from the running dashboard:

- `docs/demo/dashboard-overview.png` — Glance (KPIs + top rated samples, controls on top)
- `docs/demo/dashboard-graph.png` — Graph (all six plotly charts)
- `docs/demo/dashboard-sequence.png` — 順番に見る (sequential detail viewer: 前 / 次 / 読み上げ)

Regenerate them with `local/_demo_shots.mjs` (headless Chrome + CDP on port 9333, server on 3002). `local/` is git-ignored.

## Dashboard server (FastAPI + plotly.py)

```bash
python -m pip install -r requirements.txt
python agents/skills/viewer/server.py        # http://127.0.0.1:3002
# PORT=8080 python agents/skills/viewer/server.py
```

The server reads `docs/data/` directly and serves images from `docs/images/`. It also hides the plotly.js CDN dependency by serving the copy bundled with the installed plotly.py.

The tag network is generated with pure Python (no plotly/networkx): `/api/network.svg` returns SVG, `/api/network` returns nodes/edges, and `/network` is a standalone HTML page. The same SVG is embedded in the dashboard's **Network** tab.

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard HTML |
| `GET /viewer` | Volume metadata viewer |
| `GET /api/get?ids=LATEST` | Latest review(s); also accepts image names or indexes |
| `GET /api/reviews?tag=&category=&min_suit=&q=&limit=&offset=` | Filtered review list |
| `GET /api/stats` | Aggregates used by the dashboard |
| `GET /api/metadata` | `docs/data/metadata.json` |
| `GET /vlm` | Camera + VLM text demo |
| `GET /network` | Tag co-occurrence network (SVG page) |
| `GET /api/network` | Network nodes/edges as JSON |
| `GET /api/network.svg` | Standalone SVG (supports `?min_weight=`) |
| `GET /api/vlm/health` | VLM endpoint status (LM Studio / OpenAI compatible) |
| `POST /api/vlm` | Send an image + prompt and return the VLM text |
| `GET /healthz` | Health check |

CORS is open (`*`) so preview harnesses can poll `/api/get`.

## VLM camera demo

Open <http://localhost:3002/vlm> with the server running. The page can:

- start the device camera (`getUserMedia`) and capture a frame
- upload an image instead (camera-less fallback)
- choose a prompt preset (LoRA JSON review / Japanese description / OCR)
- send the image to `/api/vlm` and show the VLM answer in a text view
- pretty-print JSON, copy the result, or save it as `.txt`

The server proxies to an OpenAI-compatible endpoint (LM Studio by default):

```bash
VLM_BASE_URL=http://127.0.0.1:1234/v1 VLM_MODEL=tempura-qwen2.5-vl-3b python agents/skills/viewer/server.py
```

Camera access requires `localhost` or HTTPS. If the VLM is not running, the page shows `VLM未接続` and returns a readable error instead of failing silently.

## Static export (GitHub Pages)

The static `docs/dashboard.html` is generated with plotly.py and is fully self-contained: `docs/plotly.min.js` is emitted next to it from the installed plotly.py, so the page makes **no third-party requests** and works from `file://` as well. Charts render fine offline; images load from `docs/images/`.

```bash
python agents/skills/viewer/generate_report.py                 # bundled plotly.min.js (default)
python agents/skills/viewer/generate_report.py --plotly-cdn    # opt into cdn.plot.ly instead
```

`docs/plotly.min.js` (~4.7 MB) must be committed together with `docs/dashboard.html`.

## Run locally

Python 3.10+ and Pillow (for packaging):

```bash
# 1. Download one volume (writes assets/851659/ and updates docs/data/metadata.json)
python agents/skills/getter/download_ndl_iiif.py --pid 851659 --output assets

# 2. Package the compact LoRA dataset
python -m pip install Pillow
python agents/skills/packager/package_lora_dataset.py --input assets --output dist --max-side 1024 --quality 88

# 3. Build the image index for docs/viewer.html
python agents/skills/packager/build_img_index.py

# 4. Regenerate the static VLM dashboard
python agents/skills/viewer/generate_report.py

# 5. Or run the FastAPI dashboard instead
python -m pip install -r requirements.txt
python agents/skills/viewer/server.py
```

The downloader stores each volume under `assets/<PID>/` with `manifest.json`, `pages.json` and `errors.txt`. Existing files are reused on retry only when their bytes carry a recognised image signature.

## Troubleshooting

- **HTTP 403** — NDL may be denying a specific image request. This is not necessarily transient; check the record and its access conditions.
- **Unexpected Content-Type** — bytes are validated by image signature (JPEG / PNG / GIF / WebP), so HTML error pages are never saved as images.
- **Partial volume** — use `pages.json` and `errors.txt` to identify failed pages, then rerun that PID.
- **Combine step fails** — confirm each run ID still has an unexpired `hokusai-manga-volume-<PID>` artifact.

## Rights and responsible use

Check the rights and access conditions on each NDL record before training, sharing, or redistributing a derived dataset. This workflow does not bypass access controls. Requests are paced to reduce load; follow NDL's current API terms and guidance.

## IIIF endpoint

`https://dl.ndl.go.jp/api/iiif/<PID>/manifest.json`
