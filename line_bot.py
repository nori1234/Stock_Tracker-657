#!/usr/bin/env python3
"""LINE Bot Webhook サーバー — スマホから話しかけて株価を取得する。

起動 (ローカル):
    pip install -r requirements-bot.txt
    export LINE_CHANNEL_ACCESS_TOKEN=...   # push/reply 用
    export LINE_CHANNEL_SECRET=...         # 署名検証用 (LINE Developers のチャネル基本設定)
    uvicorn line_bot:app --host 0.0.0.0 --port 8000

LINE Developers Console で Webhook URL を
    https://<デプロイ先>/line/webhook
に設定し、Webhook を ON にする。あとは LINE でこの公式アカウントに
「株価」や「7203.T」と送ると返信が来る。

デプロイ先は何でもよい (Render / Railway / Cloud Run / Fly.io / 自前 VPS 等)。
コードはホスト非依存。常時起動の公開 HTTPS が 1 つあればよい。
"""
import os

from fastapi import FastAPI, Header, HTTPException, Request

from stocks import load_stock_config
from stocks.bot import handle_webhook_body, verify_signature

app = FastAPI(title="Stock Tracker LINE Bot")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/line/webhook")
async def line_webhook(request: Request, x_line_signature: str = Header(default=None)):
    body = await request.body()

    secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    if not verify_signature(secret, body, x_line_signature):
        # 署名不一致 = LINE 以外からのリクエスト。拒否する。
        raise HTTPException(status_code=403, detail="invalid signature")

    import json
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid body")

    config = load_stock_config()
    token = config.line.resolved_token()
    if not token:
        raise HTTPException(status_code=500, detail="LINE_CHANNEL_ACCESS_TOKEN 未設定")

    handle_webhook_body(payload, config, token)
    return {"ok": True}
