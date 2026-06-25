# デプロイ手順 — LINE Bot を Render に無料で立てる

スマホから「株価」と話しかけて返信をもらう **LINE Bot**（`line_bot.py`）を、
無料の [Render](https://render.com) にデプロイする具体手順。所要 10〜15 分。

> Render 以外（Railway / Cloud Run / Fly.io / 自前 VPS）でも、
> `uvicorn line_bot:app --host 0.0.0.0 --port $PORT` を常時起動できれば同じように動く。

---

## 前提

- LINE Developers で **Messaging API チャネル**を作成済み
- 控えておくもの:
  - **チャネルアクセストークン（長期）** … `LINE_CHANNEL_ACCESS_TOKEN`
  - **チャネルシークレット** … `LINE_CHANNEL_SECRET`（チャネル基本設定にある）
- このリポジトリが自分の GitHub にある（fork でも可）

---

## 手順

### 1. Render でサービスを作る（Blueprint 一発）

1. [Render](https://dashboard.render.com) にログイン（GitHub 連携）
2. **New + → Blueprint** を選択
3. このリポジトリを選ぶ → リポジトリ直下の `render.yaml` が自動検出される
4. **Apply** を押すと `stock-line-bot` という Web サービスが作られる

### 2. 機密の環境変数を入れる

`render.yaml` で `sync: false` にした 2 つは Git に載らないので、ダッシュボードで入力する。

1. サービス → **Environment** タブ
2. 次を追加:
   | Key | Value |
   |-----|-------|
   | `LINE_CHANNEL_ACCESS_TOKEN` | チャネルアクセストークン |
   | `LINE_CHANNEL_SECRET` | チャネルシークレット |
3. 保存すると自動で再デプロイされる

### 3. 公開 URL を確認する

- デプロイ完了後、サービス上部に `https://stock-line-bot-xxxx.onrender.com` の形の URL が出る
- `https://<その URL>/health` をブラウザで開き `{"status":"ok"}` が返れば起動成功

### 4. LINE に Webhook を登録する

1. LINE Developers → 対象チャネル → **Messaging API** タブ
2. **Webhook URL** に `https://<その URL>/line/webhook` を設定
3. **Webhook の利用** を **ON**
4. 「検証」ボタンで成功すれば OK
5. （任意）同画面の **応答メッセージ** を OFF にすると、定型の自動応答が消えて Bot の返信だけになる

### 5. 動作確認

LINE でこの公式アカウントを友だち追加し、「**株価**」と送る → ウォッチリストの現在値が返れば成功。
（`7203.T` のように銘柄コードを送ると個別銘柄、`ヘルプ` で使い方）

---

## 無料プランの注意（コールドスタート）

Render の無料 Web サービスは **15 分アクセスがないとスリープ**し、次のリクエストで
起動に数十秒かかる。最初の 1 通の返信が遅れる/タイムアウトすることがある。

対策（任意・どれか）:

- **気にしない**: 個人利用なら数十秒の初動遅延は許容範囲。LINE 側がリトライすることも多い。
- **定期 ping で起こしておく**: [UptimeRobot](https://uptimerobot.com) 等で
  `https://<URL>/health` を 5〜10 分おきに叩く（無料）。
- **有料プラン**にする: スリープしなくなる（月 $7〜）。

> 株価の**定期通知**（push）は GitHub Actions が担当しており、この Bot のスリープとは無関係。
> Bot はあくまで「スマホから手動で確認する」用途。

---

## トラブルシュート

| 症状 | 原因 / 対処 |
|------|------------|
| Webhook 検証が 403 | `LINE_CHANNEL_SECRET` が未設定/誤り。署名検証に失敗している |
| 返信が来ない (500) | `LINE_CHANNEL_ACCESS_TOKEN` 未設定。Render の Environment を確認 |
| 返信が常に「取得できませんでした」 | 銘柄コード表記を確認（日本株は `7203.T`） |
| 初回だけ遅い/無反応 | コールドスタート（上記の注意を参照） |
| デプロイ失敗 | Build ログを確認。`requirements-bot.txt` の解決エラーが多い |
