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
from stocks.state import AlertStateStore, hit_key


@dataclass
class RunResult:
    quotes: List[StockQuote] = field(default_factory=list)
    fired_hits: List[AlertHit] = field(default_factory=list)   # 今回成立した全条件
    hits: List[AlertHit] = field(default_factory=list)         # うち実際に通知する分 (重複抑制後)
    analyses: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    suppressed: int = 0                                        # 重複として抑制した件数
    notified: bool = False
    error_notified: bool = False                               # 取得失敗を通知したか
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


def build_error_message(errors: List[str]) -> str:
    """取得失敗をまとめた LINE 本文を組み立てる。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"⚠️ 株価取得エラー ({now})", ""]
    lines.extend(f"・{e}" for e in errors[:20])
    if len(errors) > 20:
        lines.append(f"…ほか {len(errors) - 20} 件")
    return "\n".join(lines)


def run_once(
    config: StockConfig,
    fetcher: Optional[StockFetcher] = None,
    notifier: Optional[LineNotifier] = None,
    analyst: Optional[StockAnalyst] = None,
    state_store: Optional[AlertStateStore] = None,
    cooldown_minutes: int = 0,
    notify_errors: bool = False,
    dry_run: bool = False,
) -> RunResult:
    """ウォッチリストを 1 回評価し、条件成立があれば通知する。

    fetcher / notifier を渡さなければ実物 (yfinance / LINE API) を使う。
    analyst を渡すと、発火した銘柄ごとに AI 取締役会の見解を本文へ添える。
    state_store を渡すと重複通知を抑制し、成立し続ける条件は再武装まで再送しない。
    cooldown_minutes>0 なら、最後に通知してからその時間内の再通知も抑制する
    (フラッピング対策。state_store と併用する)。
    notify_errors=True なら、株価取得に失敗した銘柄があるとき別メッセージで通知する。
    dry_run=True なら通知も状態更新も行わず、組み立てた本文を RunResult.message に返す。
    """
    fetcher = fetcher or StockFetcher()
    now = datetime.now()
    result = RunResult()

    for item in config.watchlist:
        try:
            quote = fetcher.fetch(item.symbol, name=item.name)
        except StockFetchError as e:
            result.errors.append(f"{item.symbol}: {e}")
            continue
        result.quotes.append(quote)
        result.fired_hits.extend(evaluate_alerts(quote, item.conditions))

    # 重複抑制: 前回からアクティブな条件を除外 (エッジトリガー) し、さらに
    # クールダウン中の条件も除外する。状態は dry_run 以外で更新する。
    if state_store is not None:
        new_hits, active_keys = state_store.filter_new(result.fired_hits)
        if cooldown_minutes > 0:
            new_hits = [
                h for h in new_hits
                if state_store.cooled_down(hit_key(h), now, cooldown_minutes)
            ]
        result.hits = new_hits
        result.suppressed = len(result.fired_hits) - len(result.hits)
    else:
        result.hits = list(result.fired_hits)

    # 発火した銘柄ごとに取締役会で議論させる (analyst 指定 & 通知対象がある時のみ)
    if analyst is not None and result.hits:
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

    if result.hits:
        result.message = build_message(result.hits, result.analyses)

    # 状態更新 (再武装と通知時刻の記録)。dry_run では行わない。
    if state_store is not None and not dry_run:
        state_store.commit(
            active_keys,
            notified_keys=[hit_key(h) for h in result.hits],
            now=now,
        )

    if dry_run:
        return result

    # 通知すべきものが無ければ送信しない
    notify_alert = bool(result.hits)
    notify_failure = bool(notify_errors and result.errors)
    if not notify_alert and not notify_failure:
        return result

    notifier = notifier or LineNotifier(
        token=config.line.resolved_token(),
        to=config.line.resolved_to(),
    )
    if notify_alert:
        notifier.push(result.message)
        result.notified = True
    if notify_failure:
        notifier.push(build_error_message(result.errors))
        result.error_notified = True
    return result
