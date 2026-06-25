"""LINE Bot (双方向) のロジック。

Webhook で受け取ったメッセージに応じて、その場で株価を取得して返信する。
ネットワーク I/O (fetcher / reply) は外から差し替え可能にし、署名検証と
コマンド解釈はネットワーク非依存でテストできるようにしている。

返信は LINE の **reply API** を使う (無料・無制限。月200通の push 枠を消費しない)。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Optional

from stocks.alerts import evaluate_alerts
from stocks.config import StockConfig
from stocks.fetcher import StockFetchError, StockFetcher

REPLY_URL = "https://api.line.me/v2/bot/message/reply"

HELP_TEXT = (
    "📈 使い方\n"
    "・「株価」または「一覧」… ウォッチリスト全銘柄の現在値と成立条件\n"
    "・銘柄コード (例: 7203.T / AAPL) … その銘柄の現在値\n"
    "・「ヘルプ」… この使い方"
)

_LIST_COMMANDS = {"株価", "かぶか", "一覧", "now", "check", "チェック", "list"}
_HELP_COMMANDS = {"ヘルプ", "へるぷ", "help", "?", "？"}


def verify_signature(channel_secret: str, body: bytes, signature: Optional[str]) -> bool:
    """LINE の X-Line-Signature を検証する (HMAC-SHA256 / Base64)。"""
    if not channel_secret or not signature:
        return False
    mac = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def build_reply_text(text: str, config: StockConfig, fetcher: Optional[StockFetcher] = None) -> str:
    """受信テキストに対する返信本文を組み立てる (純粋・差し替え可能)。"""
    fetcher = fetcher or StockFetcher()
    raw = (text or "").strip()
    cmd = raw.lower()

    if not raw or cmd in _HELP_COMMANDS:
        return HELP_TEXT

    if cmd in _LIST_COMMANDS:
        return _watchlist_summary(config, fetcher)

    # それ以外は銘柄コードとして扱う
    symbol = raw.upper()
    try:
        quote = fetcher.fetch(symbol)
    except StockFetchError:
        return f"「{raw}」を取得できませんでした。\n\n{HELP_TEXT}"
    return quote.format_line()


def _watchlist_summary(config: StockConfig, fetcher: StockFetcher) -> str:
    if not config.watchlist:
        return "ウォッチリストが空です。stocks.yaml に銘柄を追加してください。"
    blocks = []
    for item in config.watchlist:
        try:
            quote = fetcher.fetch(item.symbol, name=item.name)
        except StockFetchError:
            blocks.append(f"{item.name or item.symbol} ({item.symbol}): 取得失敗")
            continue
        block = quote.format_line()
        for hit in evaluate_alerts(quote, item.conditions):
            block += f"\n  ⚠️ {hit.message}"
        blocks.append(block)
    return "\n\n".join(blocks)


def reply(channel_access_token: str, reply_token: str, text: str,
          session=None, timeout: int = 10) -> None:
    """reply API で返信する。reply token は短時間で失効するためリトライしない。"""
    if session is None:
        import requests
        session = requests.Session()
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]}
    headers = {
        "Authorization": f"Bearer {channel_access_token}",
        "Content-Type": "application/json",
    }
    session.post(REPLY_URL, json=payload, headers=headers, timeout=timeout)


def handle_webhook_body(body: dict, config: StockConfig, channel_access_token: str,
                        fetcher: Optional[StockFetcher] = None, session=None) -> int:
    """webhook ペイロードを処理し、テキストメッセージに返信する。

    戻り値は返信した件数。
    """
    fetcher = fetcher or StockFetcher()
    replied = 0
    for event in body.get("events", []):
        if event.get("type") != "message":
            continue
        message = event.get("message", {})
        if message.get("type") != "text":
            continue
        reply_token = event.get("replyToken")
        if not reply_token:
            continue
        text = build_reply_text(message.get("text", ""), config, fetcher)
        reply(channel_access_token, reply_token, text, session=session)
        replied += 1
    return replied
