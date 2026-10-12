# dji2yt

Google Drive に自動アップロードされる DJI の動画を、YouTube に限定公開で自動アップロードするツール。
後処理はプラグインで差し込める（同梱: テニス）。

```
同期フォルダ / Drive API ──▶ 撮影日時で prefix リネーム（Drive に同期される）
                                        │
                     plugins.annotate()  ← 分類・再生リスト追加・タグ付け
                     plugins.derive()    ← 派生動画を生成（例: ラリーカット）
                                        │
                     YouTube へ限定公開アップロード ──▶ 再生リストに追加
```

## セットアップ

1. Google Cloud でプロジェクトを作り、**YouTube Data API v3 / Drive API / Calendar API** を有効化
2. OAuth クライアント（デスクトップアプリ）を作成し、`client_secret.json` として保存
3. インストールと認証

```bash
python -m venv .venv && .venv/bin/pip install -e .
cp config.example.toml config.toml   # folder_id などを編集
.venv/bin/dji2yt auth                # ブラウザでログイン → token.json
.venv/bin/dji2yt run --dry-run       # アップロードせずに挙動だけ確認
.venv/bin/dji2yt run
```

ffmpeg / ffprobe が PATH 上に必要（`brew install ffmpeg`）。

## 入力元

- `[local]`（Mac 推奨）: Google Drive for desktop の同期フォルダを直接読む。API でのダウンロードが不要で、
  リネームは自動で Drive に反映される。Drive のアカウントと YouTube 用に認証したアカウントが違っても OK
- `[drive]`: Drive API でダウンロード（クラウド実行向け）。日付サブフォルダもたどる

## 定期実行

- **Mac**: `deploy/com.dji2yt.plist` のパスを書き換えて `~/Library/LaunchAgents/` に置き、`launchctl load`（15 分ごと）
- **クラウド**: `Dockerfile` をビルドして Cloud Run Jobs + Cloud Scheduler で実行。
  `/data` に `config.toml` / `token.json` / `state.db` を置く（GCS マウント推奨、token は Secret Manager でも可）

## プラグイン

`dji2yt.plugins` エントリポイントで登録された `Plugin` サブクラスが読み込まれ、
`config.toml` の `[plugins] enabled` の順に実行される。

```python
from dji2yt.plugins import Plugin, VideoContext, Derivative

class MyPlugin(Plugin):
    def annotate(self, ctx: VideoContext) -> None:
        if ctx.duration > 3600:
            ctx.add_playlist("Long videos")

    def derive(self, ctx: VideoContext) -> list[Derivative]:
        return []
```

```toml
# 別パッケージの pyproject.toml
[project.entry-points."dji2yt.plugins"]
myplugin = "my_package:MyPlugin"
```

`dji2yt plugins` でインストール済みプラグインを一覧できる。

### tennis（同梱）

- 撮影時間帯と重なる Google カレンダーの予定名で **試合 / 練習** を判定し、
  `MyTennisMatch` / `MyTennisPractice` に追加する
- **ラリーカット**: 打球音（1.5kHz 以上の過渡音）を検出し、ラリー以外の時間を削った版を別動画として追加でアップロードする
- しきい値の調整は手元のファイルで行う:
  `dji2yt rallycut match.mp4 --out cut.mp4`

## 注意

- 2020/7/28 以降に作成された **未監査の API プロジェクト** からアップロードした動画は、強制的に非公開になる。
  限定公開にするには YouTube API の監査申請が必要（未監査の間はログに警告が出る）。
- `videos.insert` はクォータ消費が大きい。上限に達した場合はその回の処理を止め、残りは次回に回す。
- 処理状態は `state.db` に保存しているので、途中で失敗しても二重アップロードにはならない。
- `client_secret*.json` / `token*.json` / `config.toml` は `.gitignore` 済み。
