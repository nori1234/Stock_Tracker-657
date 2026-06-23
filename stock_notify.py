#!/usr/bin/env python3
"""Stock Tracker — 株価を取得し条件成立時に LINE 通知する CLI。

使い方:
  python stock_notify.py                 # stocks.yaml を読み、条件成立なら LINE 通知
  python stock_notify.py --dry-run       # 通知せず、現在値と組み立てた本文を表示
  python stock_notify.py --config foo.yaml

cron で定期実行する例 (平日 9-15 時に 15 分おき):
  */15 9-15 * * 1-5  cd /path/to/repo && python stock_notify.py >> stock.log 2>&1
"""
import os
import sys

# 取締役会 (titans/crewai) を使う場合のテレメトリ無効化 (import 前に設定)
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import click
from rich.console import Console
from rich.panel import Panel

from stocks import BoardStockAnalyst, load_stock_config, run_once

console = Console()


def _build_analyst(titans_config_path, use_anthropic, model_override):
    """config.yaml から brain provider を作り、取締役会アナリストを返す。"""
    from titans.utils.config_loader import create_brain_provider, load_config

    app_config = load_config(titans_config_path)
    if use_anthropic:
        app_config.brain.provider = "anthropic"
        if not app_config.brain.model.startswith("claude-"):
            app_config.brain.model = "claude-haiku-4-5-20251001"
    if model_override:
        app_config.brain.model = model_override
    # 取締役会は議題のみで議論する。RAG/記憶は無効化して軽量に保つ。
    app_config.retrieval.enabled = False
    app_config.memory.enabled = False
    brain = create_brain_provider(app_config)
    console.print(
        f"[dim]取締役会: provider={app_config.brain.provider} model={app_config.brain.model}[/dim]"
    )
    return BoardStockAnalyst(brain_provider=brain, config=app_config)


@click.command()
@click.option("--config", "config_path", default="stocks.yaml", help="設定ファイルのパス")
@click.option("--dry-run", is_flag=True, default=False,
              help="LINE 送信せず、取得値と通知本文を表示するだけ")
@click.option("--discuss", is_flag=True, default=False,
              help="発火した銘柄を AI 取締役会 (titans) に議論させ、結論を本文に添える")
@click.option("--titans-config", default="config.yaml",
              help="取締役会の設定ファイル (--discuss 時に使用)")
@click.option("--anthropic", "use_anthropic", is_flag=True, default=False,
              help="取締役会で Anthropic API を使う (ANTHROPIC_API_KEY 必須)")
@click.option("--model", "model_override", default=None,
              help="取締役会のモデルを上書き (例: claude-haiku-4-5-20251001)")
def main(config_path, dry_run, discuss, titans_config, use_anthropic, model_override):
    """ウォッチリストを 1 回評価して条件成立時に LINE 通知する。"""
    config = load_stock_config(config_path)

    if not config.watchlist:
        console.print(f"[yellow]ウォッチリストが空です。{config_path} に銘柄を追加してください。[/yellow]")
        sys.exit(1)

    analyst = None
    if discuss:
        analyst = _build_analyst(titans_config, use_anthropic, model_override)

    result = run_once(config, analyst=analyst, dry_run=dry_run)

    # 取得状況のサマリ
    for quote in result.quotes:
        console.print(quote.format_line())
    for err in result.errors:
        console.print(f"[red]取得失敗:[/red] {err}")

    if not result.hits:
        console.print("\n[dim]条件成立なし。通知は送信しませんでした。[/dim]")
        sys.exit(0)

    if dry_run:
        console.print(Panel(result.message, title="[dry-run] 送信される LINE 本文", border_style="cyan"))
        sys.exit(0)

    if result.notified:
        console.print(Panel(
            result.message,
            title=f"LINE 通知を送信しました ({len(result.hits)} 件成立)",
            border_style="green",
        ))


if __name__ == "__main__":
    main()
