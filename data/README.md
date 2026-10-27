# Hokusai Dataset — Data

浮世絵漫画 Hokusai マンガのデータセット。

## ファイル一覧

| ファイル | 説明 |
|----------|------|
| `images-resized-720/` | 114枚の画像（720px幅にリサイズ済み） |
| `hokusai_vlm_reviews.jsonl` | VLM による注釈（1行=1JSON） |
| `hokusai_vlm_reviews.db` | SQLite データベース |
| `annotations.txt` | カテゴリ説明テキスト（原典から抽出） |
| `manifest.json` | CERN/BnF 所蔵のマニフェスト |

## VLM 注釈

- **モデル**: `tempura-qwen2.5-vl-3b`
- **エンドポイント**: `http://localhost:1234/v1`
- **注釈項目**: subject, category, lora_quality (4項目), training_suitability, notes