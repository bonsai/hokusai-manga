# vlm_reviewer — VLM Review Toolkit

VLM (Vision Language Model) による画像分析ツールキット。  
浮世絵漫画 Hokusai データセットの注釈付けとレポート生成。

## モジュール一覧

| モジュール | 役割 |
|-----------|------|
| `vlm_reviewer.py` | VLM クライアント（コア） — LMStudio / Ollama 接続 |
| `batch_review.py` | 全画像一括処理 — バックグラウンドで逐次保存 |
| `review_10_batch.py` | バッチ10枚処理 — 1回実行で10枚処理 |
| `review_10_batch_autoloop.py` | 自動ループ — 全画像を10枚ずつ処理 |
| `hokusai_reviewer.py` | メインレビュー機能 |
| `generate_report.py` | ダッシュボード生成 — Plotly によるインタラクティブレポート |

## 使い方

```bash
# 10枚バッチ
python review_10_batch.py

# 全画像自動処理
python review_10_batch_autoloop.py

# ダッシュボード生成
python generate_report.py
```

## データフロー

```
images (114枚)
    │
    ▼  [vlm_reviewer.py] VLM クライアント
    │    tempura-qwen2.5-vl-3b → JSON 注釈
    │
    ▼
hokusai_vlm_reviews.jsonl  +  hokusai_vlm_reviews.db
    │
    ▼  [generate_report.py]
    │
outputs/hokusai_report.html  (Plotly ダッシュボード)
```