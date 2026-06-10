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


@click.command()
@click.argument("user_input", required=False)
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--verbose", is_flag=True, default=False, help="Enable CrewAI verbose output")
@click.option("--no-save", is_flag=True, default=False, help="Do not save output to file")
@click.option("--health-check", is_flag=True, default=False, help="Check Ollama connectivity only")
def main(user_input, config_path, verbose, no_save, health_check):
    """Titans Board v2.0 — AI Executive Board of Directors"""
    app_config = load_config(config_path)
    if verbose:
        app_config.meeting.verbose = True

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

    flow = BoardMeetingFlow(brain_provider=brain_provider, config=app_config)
    flow.kickoff(inputs={"user_input": user_input})

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
