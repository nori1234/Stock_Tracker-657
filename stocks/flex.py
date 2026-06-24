"""LINE Flex Message のコンテンツ生成 (ネットワーク非依存)。

発火した銘柄ごとに 1 つの bubble を作り、複数銘柄なら carousel にまとめる。
LINE の制約上、carousel は最大 12 bubble まで。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from stocks.alerts import AlertHit
from stocks.models import StockQuote, _currency_symbol

_MAX_BUBBLES = 12
_UP = "#D32F2F"      # 上昇は赤 (日本式) ／ 下落は緑
_DOWN = "#2E7D32"
_FLAT = "#616161"


def build_flex(hits: List[AlertHit], analyses: Optional[Dict[str, str]] = None) -> dict:
    """発火 hits から Flex の contents (bubble / carousel) を組み立てる。"""
    analyses = analyses or {}
    by_symbol: Dict[str, List[AlertHit]] = {}
    quotes: Dict[str, StockQuote] = {}
    for hit in hits:
        by_symbol.setdefault(hit.quote.symbol, []).append(hit)
        quotes[hit.quote.symbol] = hit.quote

    bubbles = [
        _bubble(quotes[sym], by_symbol[sym], analyses.get(sym))
        for sym in list(by_symbol)[:_MAX_BUBBLES]
    ]
    if len(bubbles) == 1:
        return bubbles[0]
    return {"type": "carousel", "contents": bubbles}


def alt_text(hits: List[AlertHit]) -> str:
    symbols = []
    for hit in hits:
        if hit.quote.symbol not in symbols:
            symbols.append(hit.quote.symbol)
    return "📊 株価アラート: " + " / ".join(symbols)


def _bubble(quote: StockQuote, hits: List[AlertHit], analysis: Optional[str]) -> dict:
    color = _UP if quote.change > 0 else (_DOWN if quote.change < 0 else _FLAT)
    unit = _currency_symbol(quote.currency)
    sign = "+" if quote.change >= 0 else ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    body_contents: List[dict] = [
        {
            "type": "text", "text": f"{unit}{quote.price:,.2f}",
            "size": "xxl", "weight": "bold", "color": color,
        },
        {
            "type": "text",
            "text": f"前日比 {sign}{quote.change:,.2f} ({sign}{quote.change_pct:.2f}%)",
            "size": "sm", "color": color, "margin": "sm",
        },
        {"type": "separator", "margin": "md"},
    ]

    for hit in hits:
        body_contents.append({
            "type": "text", "text": f"⚠️ {hit.message}",
            "size": "sm", "color": "#333333", "wrap": True, "margin": "sm",
        })

    if analysis:
        body_contents.append({"type": "separator", "margin": "md"})
        body_contents.append({
            "type": "text", "text": "🤖 取締役会の見解",
            "size": "xs", "color": "#888888", "margin": "md",
        })
        body_contents.append({
            "type": "text", "text": analysis,
            "size": "sm", "color": "#333333", "wrap": True, "margin": "sm",
        })

    return {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": quote.name, "weight": "bold", "size": "md",
                 "color": "#FFFFFF", "wrap": True},
                {"type": "text", "text": quote.symbol, "size": "xs", "color": "#FFFFFFCC"},
            ],
            "backgroundColor": color, "paddingAll": "12px",
        },
        "body": {
            "type": "box", "layout": "vertical", "contents": body_contents, "spacing": "none",
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "contents": [{"type": "text", "text": now, "size": "xxs", "color": "#AAAAAA"}],
        },
    }
