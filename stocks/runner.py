"""ウォッチリストを一巡し、条件を満たした銘柄だけ LINE に通知する。

ネットワーク I/O は fetcher / notifier に閉じ込め、本モジュールは
それらを差し替え可能にして組み立てだけ行う (テスト容易性のため)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from stocks.alerts import AlertHit, evaluate_alerts
from stocks.analyst import StockAnalyst
from stocks.config import StockConfig
from stocks.fetcher import StockFetchError, StockFetcher
from stocks.line_notifier import LineNotifier
from stocks.models import StockQuote
from stocks.state import AlertStateStore


@dataclass
class RunResult:
    quotes: List[StockQuote] = field(default_factory=list)
    fired_hits: List[AlertHit] = field(default_factory=list)   # 今回成立した全条件
    hits: List[AlertHit] = field(default_factory=list)         # うち実際に通知する分 (重複抑制後)
    analyses: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    suppressed: int = 0                                        # 重複として抑制した件数
    notified: bool = False
    message: str = ""


def build_message(hits: List[AlertHit], analyses: Optional[Dict[str, str]] = None) -> str:
    """発火した条件をまとめた LINE 本文を組み立てる。

    analyses が与えられれば、銘柄ごとに AI 取締役会の見解を添える。
    """
    analyses = analyses or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 株価アラート ({now})", ""]
    # 銘柄ごとにまとめる (発火順を保ちつつ重複ヘッダを避ける)
    seen: Dict[str, StockQuote] = {}
    by_symbol: Dict[str, List[AlertHit]] = {}
    for hit in hits:
        by_symbol.setdefault(hit.quote.symbol, []).append(hit)
        seen[hit.quote.symbol] = hit.quote

    for symbol, symbol_hits in by_symbol.items():
        lines.append(seen[symbol].format_line())
        for hit in symbol_hits:
            lines.append(f"  ⚠️ 条件成立: {hit.message}")
        analysis = analyses.get(symbol)
        if analysis:
            lines.append(f"  🤖 取締役会の見解:\n{_indent(analysis)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def run_once(
    config: StockConfig,
    fetcher: Optional[StockFetcher] = None,
    notifier: Optional[LineNotifier] = None,
    analyst: Optional[StockAnalyst] = None,
    state_store: Optional[AlertStateStore] = None,
    dry_run: bool = False,
) -> RunResult:
    """ウォッチリストを 1 回評価し、条件成立があれば通知する。

    fetcher / notifier を渡さなければ実物 (yfinance / LINE API) を使う。
    analyst を渡すと、発火した銘柄ごとに AI 取締役会の見解を本文へ添える。
    state_store を渡すと重複通知を抑制し、成立し続ける条件は再武装まで再送しない。
    dry_run=True なら通知も状態更新も行わず、組み立てた本文を RunResult.message に返す。
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
        result.fired_hits.extend(evaluate_alerts(quote, item.conditions))

    # 重複抑制: 前回からアクティブな条件を除外し、状態を更新 (dry_run では更新しない)
    if state_store is not None:
        result.hits, active_keys = state_store.filter_new(result.fired_hits)
        result.suppressed = len(result.fired_hits) - len(result.hits)
        if not dry_run:
            state_store.commit(active_keys)
    else:
        result.hits = list(result.fired_hits)

    if not result.hits:
        return result

    # 発火した銘柄ごとに取締役会で議論させる (analyst 指定時のみ)
    if analyst is not None:
        by_symbol: Dict[str, List[AlertHit]] = {}
        for hit in result.hits:
            by_symbol.setdefault(hit.quote.symbol, []).append(hit)
        for symbol, symbol_hits in by_symbol.items():
            try:
                view = analyst.analyze(symbol_hits[0].quote, symbol_hits)
            except Exception as e:  # 取締役会が失敗してもアラート自体は通知する
                result.errors.append(f"{symbol} の取締役会議論に失敗: {e}")
                continue
            if view:
                result.analyses[symbol] = view

    result.message = build_message(result.hits, result.analyses)

    if dry_run:
        return result

    notifier = notifier or LineNotifier(
        token=config.line.resolved_token(),
        to=config.line.resolved_to(),
    )
    notifier.push(result.message)
    result.notified = True
    return result
