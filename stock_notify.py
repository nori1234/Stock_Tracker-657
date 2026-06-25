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

from stocks import AlertStateStore, BoardStockAnalyst, load_stock_config, run_once

console = Console()


def _build_analyst(titans_config_path, provider, model, summary_only=False):
    """config.yaml から brain provider を作り、取締役会アナリストを返す。"""
    from titans.utils.config_loader import create_brain_provider, load_config

    app_config = load_config(titans_config_path)
    if provider:
        app_config.brain.provider = provider
        if provider == "anthropic" and not app_config.brain.model.startswith("claude-"):
            app_config.brain.model = "claude-haiku-4-5-20251001"
    if model:
        app_config.brain.model = model
    # 取締役会は議題のみで議論する。RAG/記憶は無効化して軽量に保つ。
    app_config.retrieval.enabled = False
    app_config.memory.enabled = False
    brain = create_brain_provider(app_config)
    console.print(
        f"[dim]取締役会: provider={app_config.brain.provider} model={app_config.brain.model}[/dim]"
    )
    return BoardStockAnalyst(brain_provider=brain, config=app_config, summary_only=summary_only)


@click.command()
@click.option("--config", "config_path", default="stocks.yaml", help="設定ファイルのパス")
@click.option("--dry-run", is_flag=True, default=False,
              help="LINE 送信せず、取得値と通知本文を表示するだけ")
@click.option("--discuss", is_flag=True, default=False,
              help="発火した銘柄を AI 取締役会 (titans) に議論させ、結論を本文に添える")
@click.option("--discuss-summary", is_flag=True, default=False,
              help="--discuss の結論を一言サマリに短縮して添える")
@click.option("--flex", "use_flex", is_flag=True, default=False,
              help="LINE Flex Message (カード表示) で送信する")
@click.option("--titans-config", default="config.yaml",
              help="取締役会の設定ファイル (--discuss 時に使用)")
@click.option("--anthropic", "use_anthropic", is_flag=True, default=False,
              help="取締役会で Anthropic API を使う (ANTHROPIC_API_KEY 必須)")
@click.option("--model", "model_override", default=None,
              help="取締役会のモデルを上書き (例: claude-haiku-4-5-20251001)")
@click.option("--no-dedup", is_flag=True, default=False,
              help="重複抑制を無効化し、成立中の条件を毎回通知する")
@click.option("--state-file", default="./storage/stock_alert_state.json",
              help="重複抑制の状態ファイルのパス")
@click.option("--cooldown-minutes", type=int, default=0,
              help="同一条件は最後の通知からこの分数だけ再通知しない (フラッピング対策)")
@click.option("--notify-errors", is_flag=True, default=False,
              help="株価取得に失敗した銘柄があるとき LINE に別途通知する")
def main(config_path, dry_run, discuss, discuss_summary, use_flex, titans_config,
         use_anthropic, model_override, no_dedup, state_file, cooldown_minutes, notify_errors):
    """ウォッチリストを 1 回評価して条件成立時に LINE 通知する。"""
    config = load_stock_config(config_path)

    if not config.watchlist:
        console.print(f"[yellow]ウォッチリストが空です。{config_path} に銘柄を追加してください。[/yellow]")
        sys.exit(1)

    # 機密の誤コミット警告: トークンは環境変数 (CI の Secrets) で渡すこと
    if config.line.has_inline_secret():
        console.print(
            f"[bold red]警告:[/bold red] {config_path} に LINE トークンが直書きされています。"
            "commit 漏洩の危険があるため、空にして環境変数 LINE_CHANNEL_ACCESS_TOKEN を使ってください。"
        )

    # 取締役会との融合: stocks.yaml の board 設定を既定にし、CLI フラグが上書きする
    board = config.board
    board_enabled = discuss or discuss_summary or board.enabled
    board_summary = discuss_summary or board.summary
    board_provider = "anthropic" if use_anthropic else board.provider
    board_model = model_override or board.model
    board_titans_config = titans_config if titans_config != "config.yaml" else board.titans_config

    analyst = None
    if board_enabled:
        analyst = _build_analyst(board_titans_config, board_provider, board_model,
                                 summary_only=board_summary)

    state_store = None if no_dedup else AlertStateStore(state_file)

    result = run_once(
        config,
        analyst=analyst,
        state_store=state_store,
        cooldown_minutes=cooldown_minutes,
        notify_errors=notify_errors,
        use_flex=use_flex,
        dry_run=dry_run,
    )

    # 取得状況のサマリ
    for quote in result.quotes:
        console.print(quote.format_line())
    for err in result.errors:
        console.print(f"[red]取得失敗:[/red] {err}")

    if result.suppressed:
        console.print(f"[dim]重複抑制: 成立中の {result.suppressed} 件は再通知をスキップ。[/dim]")

    if result.error_notified:
        console.print(f"[yellow]取得失敗 {len(result.errors)} 件を LINE に通知しました。[/yellow]")

    if not result.hits:
        if result.suppressed:
            console.print("[dim]新規の条件成立なし（成立中の条件は抑制済み）。通知は送信しませんでした。[/dim]")
        else:
            console.print("\n[dim]条件成立なし。通知は送信しませんでした。[/dim]")
        sys.exit(0)

    if dry_run:
        title = "[dry-run] 送信される LINE 本文"
        if use_flex:
            title += "（実送信は Flex カード）"
        console.print(Panel(result.message, title=title, border_style="cyan"))
        sys.exit(0)

    if result.notified:
        console.print(Panel(
            result.message,
            title=f"LINE 通知を送信しました ({len(result.hits)} 件成立)",
            border_style="green",
        ))


if __name__ == "__main__":
    main()
