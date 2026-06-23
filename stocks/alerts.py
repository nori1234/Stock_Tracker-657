"""アラート条件の評価 (純粋関数・ネットワーク非依存)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from stocks.config import AlertCondition
from stocks.models import StockQuote


@dataclass(frozen=True)
class AlertHit:
    """発火した 1 条件。"""

    quote: StockQuote
    condition: AlertCondition
    message: str


# 条件タイプ -> (発火判定, 人間向けメッセージ生成) のレジストリ
def _price_above(q: StockQuote, v: float) -> bool:
    return q.price >= v


def _price_below(q: StockQuote, v: float) -> bool:
    return q.price <= v


def _change_pct_above(q: StockQuote, v: float) -> bool:
    return q.change_pct >= v


def _change_pct_below(q: StockQuote, v: float) -> bool:
    return q.change_pct <= v


_PREDICATES: Dict[str, Callable[[StockQuote, float], bool]] = {
    "price_above": _price_above,
    "price_below": _price_below,
    "change_pct_above": _change_pct_above,
    "change_pct_below": _change_pct_below,
}

_DESCRIPTIONS: Dict[str, str] = {
    "price_above": "現在値が {value} 以上",
    "price_below": "現在値が {value} 以下",
    "change_pct_above": "前日比が {value}% 以上",
    "change_pct_below": "前日比が {value}% 以下",
}


def evaluate_alerts(quote: StockQuote, conditions: List[AlertCondition]) -> List[AlertHit]:
    """1 銘柄について発火した条件の一覧を返す。

    未知の条件タイプは無視せず ValueError を送出する (設定ミスを早期に気付くため)。
    """
    hits: List[AlertHit] = []
    for cond in conditions:
        predicate = _PREDICATES.get(cond.type)
        if predicate is None:
            raise ValueError(
                f"未知のアラート条件 type='{cond.type}'。"
                f"使用可能: {sorted(_PREDICATES)}"
            )
        if predicate(quote, cond.value):
            desc = _DESCRIPTIONS[cond.type].format(value=cond.value)
            hits.append(AlertHit(quote=quote, condition=cond, message=desc))
    return hits
