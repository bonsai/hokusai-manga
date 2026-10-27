# Hokusai VLM Dataset — Presentation Summary

## プロジェクト概要

Katsushika Hokusai（葛飾北斎）の浮世絵漫画 114点に対し、  
VLM（Vision Language Model）で注釈を付け、Plotly ダッシュボードで可視化するデータセット。

## ディレクトリ構造

```
hokusai/
├── data/                         # 📦 データ
│   ├── images-resized-720/       # 114画像
│   ├── hokusai_vlm_reviews.jsonl # VLM注釈
│   ├── hokusai_vlm_reviews.db    # SQLite
│   └── ...
├── reviewer/                     # 🔬 VLM Reviewer
│   ├── vlm_reviewer.py           # VLMクライアント
│   ├── batch_review.py           # 全画像一括処理
│   ├── review_10_batch.py        # バッチ10枚処理
│   └── review_10_batch_autoloop.py # 自動ループ
├── viewer/                       # 📊 Viewer
│   ├── generate_report.py        # Plotlyダッシュボード
│   └── hokusai_report.html       # 生成済み
└── README.md
```

## データフロー

```
images (114枚)
    │
    ▼  [reviewer/vlm_reviewer.py] VLM
    │    Qwen2.5-VL-3B → JSON注釈
    │
    ▼
data/hokusai_vlm_reviews.jsonl + .db
    │
    ▼  [viewer/generate_report.py]
    │
viewer/hokusai_report.html  ← Plotlyダッシュボード
```

## 注釈項目

- subject: 画像の説明
- category: 9カテゴリ（landscape, figure, yokai, daily_life, nature, calligraphy, action, narrative, animals）
- lora_quality: linework, contrast, composition, artifact_free（各1-10）
- training_suitability: 1-10
- notes: 問題点など

## 使用技術

- **VLM**: Qwen2.5-VL-3B (LMStudio 経由)
- **ダッシュボード**: Plotly.js（CDN）
- **データベース**: SQLite + JSONL
- **表示**: ブラウザ（HTML/JS）

## 提出物

- `reviewer/`: Pythonスクリプト一式
- `viewer/generate_report.py`: ダッシュボード生成スクリプト
- `viewer/hokusai_report.html`: 生成済みダッシュボード
- `tree.txt`: ファイルツリー
- `README.md`: プロジェクト概要