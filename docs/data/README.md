# データ（公開データ）

`docs/data/` は GitHub Pages で公開されるデータ置き場です。
`agents/` の worker はここを読み書きし、`docs/dashboard.html` / `docs/viewer.html` はここを参照します。

## ファイル一覧

| ファイル | 種類 | 説明 |
|----------|------|------|
| `metadata.json` | 入力 | 15巻の NDL PID・IIIF マニフェスト情報（`docs/viewer.html` が読む） |
| `annotations.txt` | 入力 | キャプション雛形（トリガー `hokusai_manga`） |
| `hokusai_vlm_reviews.jsonl` | 生成物 | VLM 注釈（1行=1JSON）。`agents/skills/reviewer` が出力 |
| `hokusai_vlm_reviews.db` | 生成物 | 上記の SQLite 版。`agents/skills/reviewer` が出力 |

画像は `docs/images/`（114枚、720px幅）にあります。ダッシュボードは画像を `images/<file>` で参照します。

## VLM 注釈

- **モデル**: `tempura-qwen2.5-vl-3b`
- **エンドポイント**: `http://localhost:1234/v1`
- **注釈項目**: subject, category, lora_quality (4項目), training_suitability, notes

## 再生成

```bash
# 注釈（docs/images → docs/data/hokusai_vlm_reviews.*）
python agents/skills/reviewer/review_10_batch_autoloop.py

# ダッシュボード（docs/data → docs/dashboard.html）
python agents/skills/viewer/generate_report.py
```
