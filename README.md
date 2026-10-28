# hokusai-manga

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
│   ├── images/               # 114枚のページ画像（720px幅）
│   ├── img/index.json         # viewer 用画像インデックス（packager skill が生成）
│   └── data/                 # 公開データ（metadata / annotations / VLM 注釈）
├── agents/skills/            # スキーマ（skill.yaml）+ worker（*.py）のみ
│   ├── getter/               # NDL IIIF から画像取得
│   ├── packager/             # LoRA ZIP 作成・画像インデックス生成
│   ├── reviewer/             # VLM 注釈（docs/data を更新）
│   └── viewer/               # docs/dashboard.html 生成 + FastAPI サーバ
└── .github/workflows/        # ダウンロード / GitHub Pages
```

### Rules

- `agents/` には **スキーマ (`skill.yaml`) と worker (`*.py`) だけ**を置く。HTML・データ・出力は置かない。
- `docs/` は **GitHub Pages の配信物と公開データの置き場**。成果物はここにだけ書く。
- 生成物は生成元の worker が `docs/` 配下へ出力する（手動コピーしない）。
- 一時ファイル・外部由来の大容量データは `assets/`, `dist/`, `local/`（すべて git 管理外）。
- ディレクトリ構造の記述はこの README だけに置く。

## Download all 15 volumes and create a LoRA ZIP

1. Open [Actions → Download and package Hokusai Manga for LoRA](https://github.com/bonsai/hokusai-manga/actions/workflows/download-volumes.yml).
2. Select **Run workflow** (no inputs required).
3. Wait for the run to finish. It downloads NDL PIDs `851646`–`851660` (volumes 1–15).
4. Download the `hokusai-manga-lora-dataset` artifact from the run summary.
5. Extract `hokusai_manga_lora_dataset.zip` and upload it to Kaggle as a dataset.

The ZIP contains `images/`, one same-name `.txt` caption per image, `dataset.json` provenance/size metadata, and `README.txt`. Captions use the trigger `hokusai_manga`.

### Image compression

The packaging step converts pages to RGB JPEG, resizes the longest edge to at most 1024 px, and saves at JPEG quality 88. This reduces dataset size for an initial LoRA experiment; it is a lossy conversion, so the original downloaded images and IIIF manifests are retained separately in the workflow run workspace, not committed to Git. The artifact retention period is 14 days, so download it promptly.

The workflow continues after individual page-download failures so it can package the pages that succeeded. If any download failed, the run is marked failed after the ZIP artifact is uploaded; inspect the per-volume `errors.txt` files in the artifact.

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
- **読み上げ** — speak the current detail via the Web Speech API (ja-JP / en-US auto)
- **順番に見る** — sequential viewer over the current filter/sort; use ← / → keys, Esc to close

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

Output ZIP: `dist/hokusai_manga_lora_dataset.zip`.

## Rights and responsible use

The NDL records for the original historical volumes identify these digital materials as internet-accessible; still verify the rights and access conditions on each individual record before training, sharing, or redistributing a derived dataset. This tool does not bypass access controls. Downloads are paced to avoid rapid repeated requests; follow NDL's current API terms and guidance.

## IIIF endpoints

- Manifest: `https://dl.ndl.go.jp/api/iiif/<PID>/manifest.json`
- Image requests are derived from each canvas's IIIF image service in the manifest.
