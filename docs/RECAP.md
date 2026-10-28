# Recap — ダッシュボード完成とブランチ統合

2026-10-28 セッションの作業サマリ。公開版: <https://bonsai.github.io/hokusai-manga/recap.html>

## 1. ダッシュボードを完成させた

VLM サーバーなし・既存の注釈データ（114枚 / 8件のエラー）だけで完結するようにした。

- **完全オフライン化** — `docs/plotly.min.js`（4.6MB）を plotly.py から出力し、`docs/dashboard.html` は相対参照。**外部リクエスト0件**、`file://` でも GitHub Pages でも動作。`--plotly-cdn` で従来動作も選択可。
- **検索を追加** — 1つの検索ボックスで 画像名 / 主被写体 / メモ を横断検索。Grid・List・Group に適用、`/` でフォーカス、Reset でクリア。
- **レイアウト修正** — コントロールバーを全ビューの最上部へ移動（Glance では下に落ちていた）。Glance の冗長な件数行を非表示。
- **ヘッダー情報** — `114 images / 8 errors | 4 volumes | 10 tags | Avg 6.2/10`。
- **キーボード操作** — 詳細モーダルで `Space` が読み上げの開始/停止をトグル（スクロールは抑止）。`←` / `→` で移動、`Esc` で閉じる。検索欄など入力中は無効。
- **円グラフ** — 4%未満のスライスのラベルを出さず重なりを解消。ホバーで枚数と割合を表示。

### 検証（Headless Chrome + CDP）

| 項目 | 結果 |
|---|---|
| JS エラー | 0 |
| 外部リクエスト | 0 |
| チャート描画 | 18（Graph タブ6図） |
| 画像読み込み失敗 | 0 / 494 |
| タブ | glance / grid / list / group / graph / tags / network すべて OK |
| フィルタ | landscape 54/122 · Errors 8/122 |
| 検索 | `yokai` 7件 · `turtle` 1件 |
| FastAPI | `/` 200 · `/static/plotly.min.js` 200 · `/demo/*.png` 200 |

## 2. デモ用スクリーンショット（3枚）

- `docs/demo/dashboard-overview.png` — Glance（KPI + 高評価サンプル）
- `docs/demo/dashboard-graph.png` — Graph（6図すべて）
- `docs/demo/dashboard-sequence.png` — 順番に見る（詳細・前/次・読み上げ・2/122）

`docs/index.html` に掲載。撮影は Headless Chrome + CDP（`local/_demo_shots.mjs`, `local/_demo_seq.mjs`）。

## 3. VLM テストの準備

- `agents/skills/reviewer/test_vlm_skill.py` — 接続確認 → 単一画像 → バッチ → JSONL 追記（`--limit`, `--prompt jp|en`, `--model`）。
- 実行例: `python agents/skills/reviewer/test_vlm_skill.py --limit 3 --prompt jp`
- LM Studio 側のモデルは全削除済み。VLM を試すには Vision モデルの再取得が必要（`lms get qwen/qwen2.5-vl-7b` など）。
- カメラ経路は `/vlm`（`localhost:3002/vlm`）で維持。VLM 未接続時は `VLM未接続` を表示。

## 4. ブランチ統合（PR #1: feat/one-volume-at-a-time）

main へマージ済み。コンフリクトは現行レイアウトに合わせて解消した。

| 対象 | 対応 |
|---|---|
| `download-one-volume.yml` | 1巻ずつ実行するワークフローを採用。`agents/skills/getter/download_ndl_iiif.py`, `assets/`, `docs/data/metadata.json` に合わせ、actions を v4/v5 に固定。 |
| `package-collected-volumes.yml` | 新規。run ID を指定して volume artifact を結合 → LoRA ZIP。パスを `assets/` に適応。 |
| `download_ndl_iiif.py` | 堅牢化版（画像シグネチャ検証・Referer/Accept 付与・manifest失敗を `errors.txt` に記録・壊れたローカルファイルは再取得・`content_type` 記録）。既定 `--output assets`、`--delay 1.5`（下限 0.5）。 |
| `README.md` | 現行構成を維持しつつ、1巻ずつの運用手順・Kanban・結合手順・トラブルシュートを統合。 |
| ルート `index.html` | 旧リダイレクトは破棄（Pages は `docs/index.html`）。 |

### ついでに直したバグ

`download-volumes.yml` が **不正な YAML** だった。インラインの `python3 -c "` ブロックが行頭（カラム0）から始まり `run: |` ブロックスカラーを終端させていたため、ワークフローが解析不能だった。インデント済みヒアドキュメントに置換し、全ワークフローが `yaml.safe_load` を通ることを確認。

## 5. 現在のデータ状態

- 注釈: 114枚（JSONL 252行 + SQLite）、うち 8件がエラー（タイムアウト/解析不能）。
- 巻: Vol 1–4 のみ（Vol 5–15 は未取得）。Kanban 上は Vol 2 が Doing、他は To do。
- カテゴリ: landscape 54 / daily_life 27 / yokai 15 / calligraphy 7 / nature 6 / animals 3 / figure 2。
- 品質平均: linework 7.6 / contrast 7.1 / composition 7.0 / artifact-free 6.0。

## 6. 次にやること

1. VLM テスト用の Issue を作成（環境変数・モデル・実行コマンド・JSONL スキーマ・完了条件）。
2. Vision モデルを再取得して `test_vlm_skill.py` を実走（1枚 → 3枚 → バッチ）。
3. 8件のエラーを再注釈（Issue #3 と対応）。
4. Vol 5–15 を1巻ずつ取得し、Kanban を更新（Issue #11 の整合性検証と併走）。
5. VLM 出力の `category` 正規化と `tags` 配列導入（Issue #5）。

関連 Issue: #2（plotly セルフホスト → 本セッションで実装済み）、#3, #4, #5, #11。
