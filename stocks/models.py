"""株価スナップショットのデータモデル。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StockQuote:
    """1 銘柄の現時点のスナップショット。

    日本株 (例: ``7203.T``) と米国株 (例: ``AAPL``) を同じ形で扱う。
    price / previous_close 以外は取得できないことがあり Optional。
    """

    symbol: str
    name: str
    price: float            # 現在値 (直近約定/終値)
    previous_close: float   # 前日終値
    currency: str = ""      # "JPY" / "USD" など (取得できなければ空)

    # --- 追加の市況指標 (取得できれば埋まる。アラート条件で使用) ---
    day_high: Optional[float] = None        # 当日高値
    day_low: Optional[float] = None         # 当日安値
    volume: Optional[float] = None          # 出来高
    year_high: Optional[float] = None       # 52週高値
    year_low: Optional[float] = None        # 52週安値
    ma50: Optional[float] = None            # 50日移動平均
    ma200: Optional[float] = None           # 200日移動平均

    @property
    def change(self) -> float:
        """前日終値からの変化額。"""
        return self.price - self.previous_close

    @property
    def change_pct(self) -> float:
        """前日終値からの変化率 (%)。前日終値が 0 なら 0 を返す。"""
        if not self.previous_close:
            return 0.0
        return (self.price - self.previous_close) / self.previous_close * 100.0

    def format_line(self) -> str:
        """LINE 本文向けの 1 銘柄サマリ行。"""
        arrow = "📈" if self.change > 0 else ("📉" if self.change < 0 else "➡️")
        unit = _currency_symbol(self.currency)
        sign = "+" if self.change >= 0 else ""
        return (
            f"{arrow} {self.name} ({self.symbol})\n"
            f"  現在値: {unit}{self.price:,.2f}\n"
            f"  前日比: {sign}{self.change:,.2f} ({sign}{self.change_pct:.2f}%)"
        )


def _currency_symbol(currency: str) -> str:
    return {"JPY": "¥", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency.upper(), "")
