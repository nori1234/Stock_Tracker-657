# 実運用セットアップ手順 (Stock LINE Notify)

株価アラートを LINE に自動通知するために、実際に動かすまでの手順をまとめる。
コード側 (取得 → 条件判定 → 通知 → 重複抑制 → 定期実行) は実装済み。
あとは **LINE 側の準備** と **Secrets 登録** を行えば自動運用が始まる。

---

## 1. LINE Messaging API チャネルを用意する

> LINE Notify は 2025-03-31 で終了済み。Messaging API の push を使う。

1. [LINE Developers Console](https://developers.line.biz/console/) にログイン
2. プロバイダーを作成（既存でも可）
3. **Messaging API** チャネルを新規作成
4. チャネル基本設定 →「Messaging API」タブで:
   - **チャネルアクセストークン（長期）** を発行 → これが `LINE_CHANNEL_ACCESS_TOKEN`
5. 送信先 (`LINE_TO`) を決める:
   - **個人に送る**: 作成した Bot を LINE で友だち追加し、その `userId` を取得
     （Webhook で受け取る、または公式アカウントマネージャーから確認）
   - **グループに送る**: Bot をグループに招待し、`groupId` を取得
   - ※ `LINE_TO` は `Uxxxxxxxx...`（user）または `Cxxxxxxxx...`（group）形式

---

## 2. 監視銘柄を設定する (`stocks.yaml`)

`watchlist` を自分の銘柄・条件に編集してコミットする。
トークンや送信先は **空のまま**にしておく（Secrets から環境変数で渡す）。

```yaml
line:
  channel_access_token: ""   # 空のまま。Secrets/環境変数を使う
  to: ""                     # 空のまま
watchlist:
  - symbol: "7203.T"         # 日本株は証券コード + ".T"
    name: "トヨタ自動車"
    conditions:
      - type: price_below
        value: 2500
      - type: change_pct_below
        value: -3
  - symbol: "AAPL"           # 米国株はティッカー
    conditions:
      - type: change_pct_above
        value: 5
```

条件タイプ: `price_above` / `price_below` / `change_pct_above` / `change_pct_below`

---

## 3. GitHub Actions に Secrets を登録する

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で 2 つ登録:

| Name | Value |
|------|-------|
| `LINE_CHANNEL_ACCESS_TOKEN` | 手順 1 で発行したチャネルアクセストークン |
| `LINE_TO` | 送信先の userId / groupId |

---

## 4. 疎通確認する

1. **Actions タブ → Stock LINE Notify → Run workflow**
2. `dry_run` を **ON** にして実行 → ログに取得値と「送信される本文」が出る（LINE には送らない）
3. 問題なければ `dry_run` を **OFF** で実行 → 実際に LINE に届くか確認

> 条件が成立していないと通知本文は出ない。テストしたい場合は `stocks.yaml` の
> しきい値を一時的に必ず成立する値（例: `price_below: 9999999`）にして試す。

---

## 5. 自動運用が始まる

`.github/workflows/stock-notify.yml` の `schedule` により、平日の
日本市場（JST 9:00-15:30）と米国市場（ET 9:30-17:00）の時間帯に
30 分おきで自動実行され、条件成立時に LINE 通知が届く。

- 重複抑制の状態は `actions/cache` で run 間に持ち越されるため、成立し続ける
  条件は再武装まで再通知されない。
- 実行頻度や時間帯を変えたい場合は workflow の `cron` を編集する
  （cron は UTC。JST = UTC+9）。

---

## ローカルで動かす場合 (任意)

```bash
pip install -r requirements-stock.txt          # 通知のみ (軽量)
# または pip install -r requirements.txt        # 取締役会連携 (--discuss) も使う場合

cp .env.example .env                           # LINE_CHANNEL_ACCESS_TOKEN / LINE_TO を設定
python stock_notify.py --dry-run               # 送信せず確認
python stock_notify.py                         # 本番送信
```

---

## チェックリスト

- [ ] LINE Messaging API チャネル作成・チャネルアクセストークン発行
- [ ] 送信先 (`userId` / `groupId`) を取得
- [ ] `stocks.yaml` の `watchlist` を編集してコミット
- [ ] Secrets に `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_TO` を登録
- [ ] `Run workflow` の `dry_run` で疎通確認
- [ ] `dry_run` OFF で実送信を確認
