## 概要

<!-- この PR で何をするか、なぜ必要かを 1〜3 行で -->

## 関連 Issue

- Closes #

## 変更内容

-

## 動作確認

- [ ] `pytest` が通る
- [ ] 実データに関わる変更は `dji2yt run --dry-run` で確認した（ログの要点を貼る）
- [ ]

## チェックリスト

- [ ] 変更が Issue のスコープ内に収まっている（テストを除き 500 行程度まで）
- [ ] 設定を増やした・変えた場合、`config.py` / `config.example.toml` / README を揃えた
- [ ] `state.db` のスキーマを変えた場合、既存の DB でも動く（`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE`）
- [ ] 二重アップロードや動画の消失につながる経路がない（fail closed）
- [ ] 秘密情報・実データ（トークン、フォルダ ID、メールアドレス）をコミットしていない
