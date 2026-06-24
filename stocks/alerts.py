"""アラート条件の評価 (純粋関数・ネットワーク非依存)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from stocks.config import AlertCondition
from stocks.models import StockQuote


@dataclass(frozen=True)
class AlertHit:
    """発火した 1 条件。"""

    quote: StockQuote
    condition: AlertCondition
    message: str


@dataclass(frozen=True)
class _Spec:
    """条件タイプ 1 種の仕様。"""

    predicate: Callable[[StockQuote, Optional[float]], bool]
    describe: Callable[[Optional[float]], str]
    needs_value: bool = True   # value 必須か (移動平均比較などは不要)


# value を使う基本条件 -------------------------------------------------------
def _price_above(q: StockQuote, v: float) -> bool:
    return q.price >= v


def _price_below(q: StockQuote, v: float) -> bool:
    return q.price <= v


def _change_pct_above(q: StockQuote, v: float) -> bool:
    return q.change_pct >= v


def _change_pct_below(q: StockQuote, v: float) -> bool:
    return q.change_pct <= v


def _volume_above(q: StockQuote, v: float) -> bool:
    return q.volume is not None and q.volume >= v


def _near_year_high(q: StockQuote, v: float) -> bool:
    # 52週高値の v% 以内まで近づいたら発火
    return q.year_high is not None and q.price >= q.year_high * (1 - v / 100.0)


def _near_year_low(q: StockQuote, v: float) -> bool:
    return q.year_low is not None and q.price <= q.year_low * (1 + v / 100.0)


# value を使わない移動平均比較 ------------------------------------------------
def _above_ma50(q: StockQuote, _v) -> bool:
    return q.ma50 is not None and q.price >= q.ma50


def _below_ma50(q: StockQuote, _v) -> bool:
    return q.ma50 is not None and q.price <= q.ma50


def _above_ma200(q: StockQuote, _v) -> bool:
    return q.ma200 is not None and q.price >= q.ma200


def _below_ma200(q: StockQuote, _v) -> bool:
    return q.ma200 is not None and q.price <= q.ma200


_SPECS: Dict[str, _Spec] = {
    "price_above": _Spec(_price_above, lambda v: f"現在値が {v} 以上"),
    "price_below": _Spec(_price_below, lambda v: f"現在値が {v} 以下"),
    "change_pct_above": _Spec(_change_pct_above, lambda v: f"前日比が {v}% 以上"),
    "change_pct_below": _Spec(_change_pct_below, lambda v: f"前日比が {v}% 以下"),
    "volume_above": _Spec(_volume_above, lambda v: f"出来高が {v:,.0f} 以上"),
    "near_year_high": _Spec(_near_year_high, lambda v: f"52週高値の {v}% 以内"),
    "near_year_low": _Spec(_near_year_low, lambda v: f"52週安値の {v}% 以内"),
    "above_ma50": _Spec(_above_ma50, lambda v: "現在値が50日移動平均を上回る", needs_value=False),
    "below_ma50": _Spec(_below_ma50, lambda v: "現在値が50日移動平均を下回る", needs_value=False),
    "above_ma200": _Spec(_above_ma200, lambda v: "現在値が200日移動平均を上回る", needs_value=False),
    "below_ma200": _Spec(_below_ma200, lambda v: "現在値が200日移動平均を下回る", needs_value=False),
}


def supported_types() -> List[str]:
    return sorted(_SPECS)


def evaluate_alerts(quote: StockQuote, conditions: List[AlertCondition]) -> List[AlertHit]:
    """1 銘柄について発火した条件の一覧を返す。

    未知の条件タイプ、または value 必須なのに未指定の場合は ValueError を送出する
    (設定ミスを早期に気付くため)。移動平均など指標が取得できていない条件は
    「発火しない」(False) 扱いとなり、エラーにはしない。
    """
    hits: List[AlertHit] = []
    for cond in conditions:
        spec = _SPECS.get(cond.type)
        if spec is None:
            raise ValueError(
                f"未知のアラート条件 type='{cond.type}'。使用可能: {supported_types()}"
            )
        if spec.needs_value and cond.value is None:
            raise ValueError(f"アラート条件 type='{cond.type}' には value が必要です")
        if spec.predicate(quote, cond.value):
            hits.append(AlertHit(quote=quote, condition=cond, message=spec.describe(cond.value)))
    return hits
