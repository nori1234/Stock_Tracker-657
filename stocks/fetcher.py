"""yfinance を使った株価取得。

日本株 (``7203.T``) も米国株 (``AAPL``) も同じ呼び出しで取得できる。
yfinance はネットワークアクセスを伴うため、テストではこのクラスを
スタブに差し替えて使う (runner / alerts はネットワーク非依存)。
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from stocks.models import StockQuote


class StockFetchError(RuntimeError):
    """株価の取得に失敗したとき送出。"""


class StockFetcher:
    def __init__(self, max_retries: int = 2, backoff: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep):
        # Yahoo はレート超過時に空レスポンス/例外を返すことがあるため、
        # 一時的失敗とみなして指数バックオフで数回リトライする。
        self.max_retries = max_retries
        self.backoff = backoff
        self._sleep = sleep

    def fetch(self, symbol: str, name: Optional[str] = None) -> StockQuote:
        try:
            import yfinance as yf
        except ImportError as e:  # pragma: no cover - 依存未導入時のガイド
            raise StockFetchError(
                "yfinance がインストールされていません。`pip install yfinance` を実行してください。"
            ) from e

        last_reason = "原因不明"
        for attempt in range(self.max_retries + 1):
            try:
                extracted = self._extract(yf.Ticker(symbol), symbol)
            except Exception as e:  # 通信例外等は一時的失敗とみなす
                last_reason = f"例外: {e}"
                extracted = None

            if extracted is not None:
                price = extracted["price"]
                previous_close = extracted["previous_close"]
                if price is not None and previous_close is not None:
                    return self._to_quote(symbol, name, extracted, price, previous_close)
                last_reason = "価格データが空 (レート超過/銘柄誤り の可能性)"

            if attempt < self.max_retries:
                self._sleep(self.backoff * (2 ** attempt))

        raise StockFetchError(
            f"'{symbol}' の株価を取得できませんでした ({last_reason})。シンボル表記を確認してください "
            f"(日本株は '7203.T' のように接尾辞が必要)。"
        )

    @staticmethod
    def _to_quote(symbol, name, extracted, price, previous_close) -> StockQuote:
        return StockQuote(
            symbol=symbol,
            name=name or extracted["name"] or symbol,
            price=float(price),
            previous_close=float(previous_close),
            currency=extracted["currency"] or "",
            day_high=_as_float(extracted["day_high"]),
            day_low=_as_float(extracted["day_low"]),
            volume=_as_float(extracted["volume"]),
            year_high=_as_float(extracted["year_high"]),
            year_low=_as_float(extracted["year_low"]),
            ma50=_as_float(extracted["ma50"]),
            ma200=_as_float(extracted["ma200"]),
        )

    @staticmethod
    def _extract(ticker, symbol: str) -> dict:
        """yfinance の Ticker から各種指標を取り出す。

        fast_info を優先し、現在値/前日終値が欠損するときだけ .info にフォールバックする。
        追加指標 (移動平均・高安・出来高) は fast_info から取得できる範囲で埋める。
        """
        out = {
            "price": None, "previous_close": None, "currency": None, "name": None,
            "day_high": None, "day_low": None, "volume": None,
            "year_high": None, "year_low": None, "ma50": None, "ma200": None,
        }

        fast = getattr(ticker, "fast_info", None)
        if fast is not None:
            out["price"] = _safe_get(fast, "last_price")
            out["previous_close"] = _safe_get(fast, "previous_close")
            out["currency"] = _safe_get(fast, "currency")
            out["day_high"] = _safe_get(fast, "day_high")
            out["day_low"] = _safe_get(fast, "day_low")
            out["volume"] = _safe_get(fast, "last_volume")
            out["year_high"] = _safe_get(fast, "year_high")
            out["year_low"] = _safe_get(fast, "year_low")
            out["ma50"] = _safe_get(fast, "fifty_day_average")
            out["ma200"] = _safe_get(fast, "two_hundred_day_average")

        if out["price"] is None or out["previous_close"] is None:
            info = {}
            try:
                info = ticker.info or {}
            except Exception:
                info = {}
            if out["price"] is None:
                out["price"] = info.get("regularMarketPrice")
            if out["previous_close"] is None:
                out["previous_close"] = (
                    info.get("regularMarketPreviousClose") or info.get("previousClose")
                )
            out["currency"] = out["currency"] or info.get("currency")
            out["name"] = info.get("shortName") or info.get("longName")
            # info 側にしか無い指標も拾えれば拾う
            out["day_high"] = out["day_high"] or info.get("dayHigh")
            out["day_low"] = out["day_low"] or info.get("dayLow")
            out["volume"] = out["volume"] or info.get("volume")
            out["year_high"] = out["year_high"] or info.get("fiftyTwoWeekHigh")
            out["year_low"] = out["year_low"] or info.get("fiftyTwoWeekLow")
            out["ma50"] = out["ma50"] or info.get("fiftyDayAverage")
            out["ma200"] = out["ma200"] or info.get("twoHundredDayAverage")

        return out


def _safe_get(fast_info, key: str):
    """fast_info は dict 風だがキー欠損で例外を投げる実装があるため握りつぶす。"""
    try:
        value = fast_info[key] if key in fast_info else getattr(fast_info, key, None)
    except Exception:
        return None
    return value


def _as_float(value):
    """None でなければ float に。変換できなければ None。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
