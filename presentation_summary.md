# Hokusai VLM Dataset — Presentation Summary

## プロジェクト概要

Katsushika Hokusai（葛飾北斎）の浮世絵漫画 114点に対し、VLM（Vision Language Model）で注釈を付け、Plotly ダッシュボードで可視化するデータセット。

ディレクトリ構造・実行手順は [`README.md`](README.md) を唯一の情報源とする。

## データフロー

```
docs/images/ (114枚)
    │
    ▼  agents/skills/reviewer/  (VLM: Qwen2.5-VL-3B via LM Studio)
    │
docs/data/hokusai_vlm_reviews.jsonl + .db
    │
    ▼  agents/skills/viewer/generate_report.py
    │
docs/dashboard.html  (Plotly ダッシュボード)
```

## 注釈項目

- subject: 画像の説明
- category: 9カテゴリ（landscape, figure, yokai, daily_life, nature, calligraphy, action, narrative, animals）
- lora_quality: linework, contrast, composition, artifact_free（各1-10）
- training_suitability: 1-10
- notes: 問題点など

## 使用技術

- **VLM**: Qwen2.5-VL-3B（LM Studio 経由）
- **ダッシュボード**: Plotly.js（CDN）
- **データベース**: SQLite + JSONL
- **表示**: ブラウザ（HTML/JS）

## 提出物

- `agents/skills/reviewer/`: VLM 注釈 worker とスキーマ
- `agents/skills/viewer/generate_report.py`: ダッシュボード生成スクリプト
- `docs/dashboard.html`: 生成済みダッシュボード
- `docs/data/`: 注釈データ（JSONL / SQLite / metadata）
- `README.md`: プロジェクト概要と唯一の構造説明
