"""株価アラートを AI 取締役会 (titans) に議論させる連携。

アラートが発火した銘柄を「議題」に変換し、BoardMeetingFlow
(CFO→CLO→CEO草稿→監査役→CEO最終) にかけて投資判断の結論を得る。

設計方針:
    - 取締役会の実行は実 LLM (Ollama/Anthropic) を要するため、
      runner からは ``StockAnalyst`` プロトコル越しに呼ぶ。
    - テストでは Fake アナリストを注入し、ネットワーク非依存を保つ。
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from stocks.alerts import AlertHit
from stocks.models import StockQuote


@runtime_checkable
class StockAnalyst(Protocol):
    """発火した銘柄に対する見解 (テキスト) を返す。"""

    def analyze(self, quote: StockQuote, hits: List[AlertHit]) -> str:
        ...


def build_agenda(quote: StockQuote, hits: List[AlertHit]) -> str:
    """銘柄スナップショットと発火条件から取締役会の議題文を作る。"""
    sign = "+" if quote.change >= 0 else ""
    triggers = "、".join(h.message for h in hits) or "（条件指定なし）"
    return (
        f"以下の保有候補銘柄について、買い増し・保有・売却のいずれを取るべきか"
        f"投資判断を議論し、結論と根拠を簡潔に示してください。\n\n"
        f"銘柄: {quote.name} ({quote.symbol})\n"
        f"現在値: {quote.price:,.2f} {quote.currency}\n"
        f"前日比: {sign}{quote.change:,.2f} ({sign}{quote.change_pct:.2f}%)\n"
        f"発火したアラート条件: {triggers}"
    )


class BoardStockAnalyst:
    """BoardMeetingFlow を使って投資判断の結論 (CEO最終) を返すアナリスト。"""

    def __init__(self, brain_provider, config, knowledge_base=None, memory_store=None,
                 max_chars: int = 800):
        self._brain_provider = brain_provider
        self._config = config
        self._knowledge_base = knowledge_base
        self._memory_store = memory_store
        self._max_chars = max_chars

    def analyze(self, quote: StockQuote, hits: List[AlertHit]) -> str:
        # import を遅延させ、stocks 単体利用時に crewai を要求しないようにする
        from titans.flows.board_meeting_flow import BoardMeetingFlow

        agenda = build_agenda(quote, hits)
        flow = BoardMeetingFlow(
            brain_provider=self._brain_provider,
            config=self._config,
            knowledge_base=self._knowledge_base,
            memory_store=self._memory_store,
        )
        flow.kickoff(inputs={"user_input": agenda})

        report = flow.state.meeting_report
        if report is None or not report.ceo_final_output:
            return ""
        conclusion = report.ceo_final_output.strip()
        if len(conclusion) > self._max_chars:
            conclusion = conclusion[: self._max_chars] + "…"
        return conclusion
