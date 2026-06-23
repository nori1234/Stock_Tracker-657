#!/usr/bin/env python3
"""Stock Tracker — 株価を取得し条件成立時に LINE 通知する CLI。

使い方:
  python stock_notify.py                 # stocks.yaml を読み、条件成立なら LINE 通知
  python stock_notify.py --dry-run       # 通知せず、現在値と組み立てた本文を表示
  python stock_notify.py --config foo.yaml

cron で定期実行する例 (平日 9-15 時に 15 分おき):
  */15 9-15 * * 1-5  cd /path/to/repo && python stock_notify.py >> stock.log 2>&1
"""
import sys

import click
from rich.console import Console
from rich.panel import Panel

from stocks import load_stock_config, run_once

console = Console()


@click.command()
@click.option("--config", "config_path", default="stocks.yaml", help="設定ファイルのパス")
@click.option("--dry-run", is_flag=True, default=False,
              help="LINE 送信せず、取得値と通知本文を表示するだけ")
def main(config_path, dry_run):
    """ウォッチリストを 1 回評価して条件成立時に LINE 通知する。"""
    config = load_stock_config(config_path)

    if not config.watchlist:
        console.print(f"[yellow]ウォッチリストが空です。{config_path} に銘柄を追加してください。[/yellow]")
        sys.exit(1)

    result = run_once(config, dry_run=dry_run)

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
