"""yfinance を使った株価取得。

日本株 (``7203.T``) も米国株 (``AAPL``) も同じ呼び出しで取得できる。
yfinance はネットワークアクセスを伴うため、テストではこのクラスを
スタブに差し替えて使う (runner / alerts はネットワーク非依存)。
"""
from __future__ import annotations

from typing import Optional

from stocks.models import StockQuote


class StockFetchError(RuntimeError):
    """株価の取得に失敗したとき送出。"""


class StockFetcher:
    def fetch(self, symbol: str, name: Optional[str] = None) -> StockQuote:
        try:
            import yfinance as yf
        except ImportError as e:  # pragma: no cover - 依存未導入時のガイド
            raise StockFetchError(
                "yfinance がインストールされていません。`pip install yfinance` を実行してください。"
            ) from e

        ticker = yf.Ticker(symbol)
        price, previous_close, currency, fetched_name = self._extract(ticker, symbol)

        if price is None or previous_close is None:
            raise StockFetchError(
                f"'{symbol}' の株価を取得できませんでした。シンボル表記を確認してください "
                f"(日本株は '7203.T' のように接尾辞が必要)。"
            )

        return StockQuote(
            symbol=symbol,
            name=name or fetched_name or symbol,
            price=float(price),
            previous_close=float(previous_close),
            currency=currency or "",
        )

    @staticmethod
    def _extract(ticker, symbol: str):
        """yfinance の Ticker から (現在値, 前日終値, 通貨, 名称) を取り出す。

        fast_info を優先し、欠損時は .info にフォールバックする。
        """
        price = previous_close = currency = name = None

        fast = getattr(ticker, "fast_info", None)
        if fast is not None:
            price = _safe_get(fast, "last_price")
            previous_close = _safe_get(fast, "previous_close")
            currency = _safe_get(fast, "currency")

        if price is None or previous_close is None:
            info = {}
            try:
                info = ticker.info or {}
            except Exception:
                info = {}
            price = price if price is not None else info.get("regularMarketPrice")
            previous_close = (
                previous_close
                if previous_close is not None
                else info.get("regularMarketPreviousClose") or info.get("previousClose")
            )
            currency = currency or info.get("currency")
            name = info.get("shortName") or info.get("longName")

        return price, previous_close, currency, name


def _safe_get(fast_info, key: str):
    """fast_info は dict 風だがキー欠損で例外を投げる実装があるため握りつぶす。"""
    try:
        value = fast_info[key] if key in fast_info else getattr(fast_info, key, None)
    except Exception:
        return None
    return value
