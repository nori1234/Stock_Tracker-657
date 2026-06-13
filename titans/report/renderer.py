import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule


@dataclass
class MeetingReport:
    user_input: str
    cfo_output: str
    clo_output: str
    ceo_draft_output: str
    auditor_output: str
    ceo_final_output: str
    retrieved_knowledge: str = ""
    long_term_memory: str = ""


class ReportRenderer:
    _SECTIONS = [
        ("cfo",       "CFO 財務分析",         "green",        "cfo_output"),
        ("clo",       "CLO 法務レビュー",      "yellow",       "clo_output"),
        ("ceo_draft", "CEO 戦略草稿",          "blue",         "ceo_draft_output"),
        ("auditor",   "監査役レポート",         "red",          "auditor_output"),
        ("ceo_final", "CEO 最終判断（確定版）", "bold magenta", "ceo_final_output"),
    ]

    def render_to_console(self, report: MeetingReport) -> None:
        console = Console()
        console.print(Rule("[bold]Titans Board v2.0 — 取締役会議事録[/bold]"))
        if report.long_term_memory:
            console.print(Panel(
                Markdown(report.long_term_memory),
                title="[dim]長期記憶（Memory Loader）[/dim]",
                border_style="dim",
            ))
        if report.retrieved_knowledge:
            console.print(Panel(
                Markdown(report.retrieved_knowledge),
                title="[dim]参照知識（RAG検索結果）[/dim]",
                border_style="dim",
            ))
        for _, title, color, attr in self._SECTIONS:
            content = getattr(report, attr, "")
            console.print(Panel(
                Markdown(content),
                title=f"[{color}]{title}[/{color}]",
                border_style=color,
            ))

    def save_to_file(self, report: MeetingReport, output_dir: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"meeting_{ts}.json"
        data = {
            "timestamp": ts,
            "user_input": report.user_input,
            "retrieved_knowledge": report.retrieved_knowledge,
            "long_term_memory": report.long_term_memory,
            "sections": {
                "cfo": report.cfo_output,
                "clo": report.clo_output,
                "ceo_draft": report.ceo_draft_output,
                "auditor": report.auditor_output,
                "ceo_final": report.ceo_final_output,
            },
        }
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path
