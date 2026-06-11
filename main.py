#!/usr/bin/env python3
"""
Titans Board v2.0 — Phase 1 MVP
Usage: python main.py "ここに経営課題を入力"
"""
import sys

import click
from rich.console import Console
from rich.panel import Panel

from titans.flows.board_meeting_flow import BoardMeetingFlow
from titans.report.renderer import ReportRenderer
from titans.utils.config_loader import create_brain_provider, load_config

console = Console()


def _create_knowledge_base(app_config):
    from titans.retrieval.knowledge_base import KnowledgeBase
    return KnowledgeBase(
        storage_dir=app_config.retrieval.storage_dir,
        embedder_kind=app_config.retrieval.embedder,
        embedding_dim=app_config.retrieval.embedding_dim,
        ollama_base_url=app_config.brain.base_url,
    )


@click.command()
@click.argument("user_input", required=False)
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--verbose", is_flag=True, default=False, help="Enable CrewAI verbose output")
@click.option("--no-save", is_flag=True, default=False, help="Do not save output to file")
@click.option("--health-check", is_flag=True, default=False, help="Check Ollama connectivity only")
@click.option("--ingest", "ingest_dir", default=None, help="知識ディレクトリ(.txt/.md)をRAGストアに取り込んで終了")
@click.option("--no-rag", is_flag=True, default=False, help="RAG検索を無効化して会議を実行")
def main(user_input, config_path, verbose, no_save, health_check, ingest_dir, no_rag):
    """Titans Board v2.0 — AI Executive Board of Directors"""
    app_config = load_config(config_path)
    if verbose:
        app_config.meeting.verbose = True
    if no_rag:
        app_config.retrieval.enabled = False

    if ingest_dir:
        kb = _create_knowledge_base(app_config)
        n = kb.ingest_directory(ingest_dir)
        counts = kb.count()
        kb.close()
        console.print(Panel(
            f"取り込みチャンク数: {n}\nQdrant: {counts['qdrant']} 件 / BM25: {counts['bm25']} 件",
            title="知識取り込み完了",
            border_style="green",
        ))
        sys.exit(0)

    brain_provider = create_brain_provider(app_config)

    if health_check:
        ok = brain_provider.health_check()
        info = brain_provider.model_info()
        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        console.print(Panel(
            f"Status: {status}\nModel info: {info}\nBase URL: {app_config.brain.base_url}",
            title="Ollama Health Check",
        ))
        sys.exit(0 if ok else 1)

    if not user_input:
        console.print("[red]Error:[/red] 経営課題を引数として渡してください。")
        console.print('Usage: python main.py "ここに経営課題を入力"')
        sys.exit(1)

    console.print(Panel(
        f"[bold]経営課題:[/bold] {user_input}",
        title="Titans Board v2.0 — 取締役会開始",
        border_style="bold blue",
    ))

    knowledge_base = None
    if app_config.retrieval.enabled:
        knowledge_base = _create_knowledge_base(app_config)

    flow = BoardMeetingFlow(
        brain_provider=brain_provider,
        config=app_config,
        knowledge_base=knowledge_base,
    )
    flow.kickoff(inputs={"user_input": user_input})
    if knowledge_base is not None:
        knowledge_base.close()

    report = flow.state.meeting_report
    if report is None:
        console.print("[red]エラー: レポートの生成に失敗しました。[/red]")
        sys.exit(1)

    renderer = ReportRenderer()
    renderer.render_to_console(report)

    if not no_save and app_config.output.save_to_file:
        saved_path = renderer.save_to_file(report, app_config.output.output_dir)
        console.print(f"\n[dim]レポートを保存しました: {saved_path}[/dim]")


if __name__ == "__main__":
    main()
