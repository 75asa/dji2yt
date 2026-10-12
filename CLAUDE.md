# dji2yt — developer notes

DJI の動画（Google Drive for desktop の同期フォルダ、または Drive API）を、撮影日時を頭に付けた名前にリネームし、
YouTube に限定公開でアップロードして再生リストに入れる個人用ツール。後処理はプラグイン（同梱: `tennis`）。

まず読むもの: README.md、引き継ぎ Issue（#1）、GitHub Project のボード。

## 構成

- `src/dji2yt/pipeline.py` — 1 本ずつ: 取得 → probe → リネーム → `annotate` → `derive` → アップロード → 再生リスト
- `src/dji2yt/sources.py` — `LocalSource`（同期フォルダ。Mac の推奨）/ `DriveSource`（Drive API。クラウド向け）
- `src/dji2yt/youtube.py` — resumable upload、再生リスト、`QuotaExceeded`
- `src/dji2yt/state.py` — SQLite（`state.db`）。再実行で二重アップロードしないための記録
- `src/dji2yt/plugins/` — プラグイン API（entry point `dji2yt.plugins`）と `tennis`（カレンダー判定 + 打球音のラリーカット）
- `config.example.toml` — 設定の見本。実際の `config.toml` はコミットしない

## コマンド

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/dji2yt run --dry-run --limit 3      # リネーム・アップロードをせずに確認
.venv/bin/dji2yt rallycut <file> --out cut.mp4  # ラリー検出の調整用
```

ffmpeg / ffprobe が必要（`brew install ffmpeg`）。テストの一部も ffmpeg を呼ぶ。

## 作業の約束

- PR は必ず **draft** で作る。checks とレビューが済んでから ready にする。
- 1 Issue = 1 PR。最新の `main` からブランチを切る。テストを除いて 500 行程度まで（超えるなら分割）。
- 秘密情報をコミットしない: `client_secret*.json` / `token*.json` / `config.toml` / `state.db` は `.gitignore` 済み。
  キーっぽい文字列（長いランダム文字列、ベンダーの「例」のキーも）をコード・テスト・ドキュメントに書かない。
  テストでは `SENTINEL_…` のような読める値を使う。
- 実データ（動画、Drive のフォルダ ID、メールアドレス、カレンダーの予定名）をリポジトリに入れない。
  例を書くときは `you@example.com` や `<drive-folder-id>` にする。
- アップロードは YouTube のクォータ（1 日 10,000 ユニット、`videos.insert` 1 回 1,600）を消費する。
  実データでの動作確認は `--dry-run` から始め、本番実行は持ち主に確認してから。
- 動画を失う・二重にアップロードする方向の変更は fail closed（迷ったら処理しない）にする。
- モデルの使い分け: 実装と編集はメインのモデルで行う。Issue の下書きや調査の並列作業はサブエージェント（Sonnet）、
  設計レビューと指示は Opus。
