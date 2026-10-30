# Hokusai Manga VLM Dashboard — Issue Backlog

> このファイルは GitHub Issues の代わりとして機能します。優先度順に整理しています。

---

## 🔥 High Priority (今すぐ着手)

### #1 VLM サーバーの永続化・自動起動
**現状**: `python agents/skills/vlm_server/server.py --port 3100` で手動起動が必要  
**要望**: systemd / Windows サービス / Docker Compose で常駐化  
**関連**: `agents/skills/vlm_server/`

### #2 環境変数の `.env` ファイル対応
**現状**: `setx` で Windows 環境変数に設定必須  
**要望**: リポジトリ直下の `.env` を自動読み込み（`python-dotenv`）  
**優先度**: 高（オンボーディング障壁）

### #3 `/query` ページの URL パラメータ共有機能
**現状**: フィルタ状態が URL に反映されない  
**要望**: `?q=踊り&cat=daily_life&suit_min=7` 形式で共有可能に

### #4 既存レビューの「踊り」タグ付けバッチ処理
**現状**: 114件のレビューに `dance` 判定がない  
**要望**: `dance` プリセットで全画像を再解析し、JSONL に追記  
**関連**: `agents/skills/reviewer/`

---

## 🎯 Medium Priority (次のスプリント)

### #5 VLM プロンプトのバージョン管理・A/B テスト
- プロンプトテンプレートを `prompts/` 以下で管理
- 実行時にバージョン指定可能に
- 結果比較用のメトリクス収集

### #6 `/query` 結果の一括エクスポート
- CSV / JSONL / COCO 形式でダウンロード
- 選択項目のみ / フィルタ適用済み全件

### #7 画像の遅延読み込み最適化
- `/query` のサムネイルグリッドで `IntersectionObserver` 実装済みだが、プレースホルダー改善
- WebP 対応・適応的サイズ

### #8 Dashboard の「踊り」専用フィルタ/可視化
- タグネットワークに `dance` ノード追加
- グラフに踊りカテゴリ別の適合度分布

### #9 エラーページの親切化
- 404 / 500 / VLM接続失敗時のガイダンス改善
- `/healthz` 詳細モード追加

### #10 ログビューアの「お気に入り/メモ」機能
- 個別レビューに星印・メモ付与
- LocalStorage で永続化

---

## 💡 Low Priority / Nice to Have

### #11 多言語 UI 対応（英語/日本語切替）
- i18n フレームワーク導入（軽量な自前実装で可）

### #12 キーボードショートカット完全対応
- `/query`: `j/k` 選択移動, `Enter` 詳細, `/` 検索フォーカス
- `/vlm`: `Space` 撮影, `r` リセット 等

### #13 オフライン対応 (PWA)
- Service Worker で静的アセットキャッシュ
- オフライン時も `/logs` `/query` 閲覧可能に

### #14 検索の高度化
- SQLite FTS5 導入（`sqlite-vec` でベクトル検索も視野に）
- 「似た構図」「似た筆致」の類似検索

### #15 レビューアノテーション UI
- 画像上にバウンディングボックス描画
- タグ付け支援（推奨タグ表示）

### #16 CI/CD での自動テスト
- `pytest` で API エンドポイントテスト
- Playwright で E2E テスト（`/vlm` カメラモック込み）

### #17 ドキュメント整備
- `docs/architecture.md`: システム全体図
- `docs/api.md`: OpenAPI 自動生成
- `docs/prompts.md`: プロンプト設計指針

---

## 🐛 Bugs / Known Issues

### BUG-1: ポート競合時のエラーハンドリング
- 3002-3010 まで試しても `Errno 10048` で落ちる
- 自動で空きポート探索 or 明確なエラーメッセージ

### BUG-2: `/logs` で巨大 JSONL 読み込み時のメモリ
- 現状全件メモリ展開 → ストリーミング / ページネーション API 化

### BUG-3: VLM ヘルスチェックのキャッシュ問題
- 15秒間隔だが、失敗時のリトライロジックが甘い
- 指数バックオフ実装

### BUG-4: 音声通知がモバイルで鳴らない
- `AudioContext` はユーザー操作後に resume 必要
- 初回クリック時に `audioCtx.resume()` 呼び出し

---

## 📦 Technical Debt

### TD-1: `server.py` の肥大化（700行超）
- ルーター分割: `routes_query.py`, `routes_logs.py`, `routes_vlm.py` 等
- `generate_report.py` との共有コード整理

### TD-2: インライン HTML/JS の外部化
- `QUERY_PAGE`, `LOGS_PAGE`, `LINKS_PAGE` 等をテンプレートエンジン化
- 開発時は HMR 対応（Vite 等）

### TD-3: 型ヒントの不足
- `pydantic` モデルで API 入出力完全型付け
- `mypy` 導入・CI 組み込み

### TD-4: 設定の一元化
- `config.yaml` / `settings.py` でポート・パス・デフォルト値管理
- 環境別（dev/staging/prod）切替

---

## 🚀 Future Ideas (v2.0+)

- **マルチモデル対応**: 画像分類器（CLIP等）+ VLM のハイブリッド
- **アノテーション共同作業**: 複数ユーザーでレビュー・合議
- **LoRA 学習パイプライン統合**: 選抜画像 → 学習ジョブ投入 → モデル評価
- **IIIF Manifest ビューア統合**: `/viewer` でミラーページ・メタデータ連携
- **プロンプトエンジニアリング支援**: 少数ショット例の自動選抜・効果測定

---

## 📝 How to Use

1. **GitHub Issues に移行する場合**: 各セクションを個別 Issue に分割
2. **ラベル推奨**: `priority:high`, `priority:medium`, `priority:low`, `bug`, `enhancement`, `tech-debt`, `docs`
3. **マイルストーン**: `v1.1` (High), `v1.2` (Medium), `v2.0` (Future)

---

> Last updated: 2026-10-29  
> Generated from development session