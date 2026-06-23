"""ウォッチリストを一巡し、条件を満たした銘柄だけ LINE に通知する。

ネットワーク I/O は fetcher / notifier に閉じ込め、本モジュールは
それらを差し替え可能にして組み立てだけ行う (テスト容易性のため)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from stocks.alerts import AlertHit, evaluate_alerts
from stocks.config import StockConfig
from stocks.fetcher import StockFetchError, StockFetcher
from stocks.line_notifier import LineNotifier
from stocks.models import StockQuote


@dataclass
class RunResult:
    quotes: List[StockQuote] = field(default_factory=list)
    hits: List[AlertHit] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    notified: bool = False
    message: str = ""


def build_message(hits: List[AlertHit]) -> str:
    """発火した条件をまとめた LINE 本文を組み立てる。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 株価アラート ({now})", ""]
    # 銘柄ごとにまとめる (発火順を保ちつつ重複ヘッダを避ける)
    seen: dict[str, StockQuote] = {}
    by_symbol: dict[str, List[AlertHit]] = {}
    for hit in hits:
        by_symbol.setdefault(hit.quote.symbol, []).append(hit)
        seen[hit.quote.symbol] = hit.quote

    for symbol, symbol_hits in by_symbol.items():
        lines.append(seen[symbol].format_line())
        for hit in symbol_hits:
            lines.append(f"  ⚠️ 条件成立: {hit.message}")
        lines.append("")
    return "\n".join(lines).rstrip()


def run_once(
    config: StockConfig,
    fetcher: Optional[StockFetcher] = None,
    notifier: Optional[LineNotifier] = None,
    dry_run: bool = False,
) -> RunResult:
    """ウォッチリストを 1 回評価し、条件成立があれば通知する。

    fetcher / notifier を渡さなければ実物 (yfinance / LINE API) を使う。
    dry_run=True なら通知は行わず、組み立てた本文を RunResult.message に返す。
    """
    fetcher = fetcher or StockFetcher()
    result = RunResult()

    for item in config.watchlist:
        try:
            quote = fetcher.fetch(item.symbol, name=item.name)
        except StockFetchError as e:
            result.errors.append(f"{item.symbol}: {e}")
            continue
        result.quotes.append(quote)
        result.hits.extend(evaluate_alerts(quote, item.conditions))

    if not result.hits:
        return result

    result.message = build_message(result.hits)

    if dry_run:
        return result

    notifier = notifier or LineNotifier(
        token=config.line.resolved_token(),
        to=config.line.resolved_to(),
    )
    notifier.push(result.message)
    result.notified = True
    return result
