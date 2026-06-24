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
                 max_chars: int = 800, summary_only: bool = False):
        self._brain_provider = brain_provider
        self._config = config
        self._knowledge_base = knowledge_base
        self._memory_store = memory_store
        self._max_chars = max_chars
        self._summary_only = summary_only   # True なら結論を一言サマリに短縮

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
        if self._summary_only:
            return summarize_conclusion(conclusion)
        if len(conclusion) > self._max_chars:
            conclusion = conclusion[: self._max_chars] + "…"
        return conclusion


def summarize_conclusion(text: str, max_chars: int = 120) -> str:
    """取締役会の結論を「一言サマリ」に短縮する。

    LLM を追加で呼ばず、最初の意味のある一文を取り出す簡易要約。
    箇条書き記号や見出しを除き、最初の文末 (。!?) までを返す。
    """
    for raw in text.splitlines():
        stripped = raw.strip()
        # 見出し行 (# / ＃ で始まる) は本文ではないので飛ばす
        if not stripped or stripped[0] in "#＃":
            continue
        line = stripped.lstrip("-*・•#＃ 　").strip()
        if not line:
            continue
        # 最初の文末記号までを 1 文として取り出す
        for i, ch in enumerate(line):
            if ch in "。．.!?！？":
                sentence = line[: i + 1].strip()
                break
        else:
            sentence = line
        if len(sentence) > max_chars:
            sentence = sentence[:max_chars] + "…"
        return sentence
    return ""
