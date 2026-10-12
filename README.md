# dji2yt

Google Drive に自動アップロードされる DJI の動画を YouTube に自動公開するパイプライン。

## やること

1. Drive の監視フォルダから新しい `.mp4` を取得
2. 撮影日時を prefix にリネーム（例: `2026-10-12_1530_DJI_0001.mp4`）
3. YouTube に **限定公開** でアップロード（resumable upload）
4. 再生リストに追加（日付ごと / 共通）
5. テニスの動画は Google カレンダーの予定と撮影時刻を突き合わせて
   `MyTennisMatch` / `MyTennisPractice` にも追加
6. （任意）打球音検出でポイント間のデッドタイムをカットしたダイジェスト版も作成

## 構成

```
src/dji2yt/
  config.py      設定（フォルダ ID、再生リスト名など）
  drive.py       Drive から新規動画を列挙・ダウンロード
  naming.py      撮影日時の抽出とリネーム
  youtube.py     アップロード・再生リスト操作
  classify.py    カレンダー照合でテニス試合/練習を判定
  rallycut.py    打球音検出によるラリー切り出し
  state.py       処理済み管理（二重アップロード防止）
  main.py        エントリポイント
```

## 実行環境

ローカル（Mac + launchd）でもクラウド（Cloud Run Jobs + Cloud Scheduler）でも
同じコンテナで動くようにする。

## 注意

- 2020/7/28 以降に作成された未監査の API プロジェクトからアップロードした動画は
  強制的に非公開になる。限定公開にするには YouTube API の監査申請が必要。
- `videos.insert` はクォータ消費が大きく、デフォルト枠だと 1 日数本が上限。
- OAuth のクライアントシークレットやトークンは絶対にコミットしないこと。
