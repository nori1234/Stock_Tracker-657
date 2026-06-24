"""株価を取得し、条件を満たしたら LINE に通知するモジュール。

titans (AI 取締役会) からの段階的な置き換えとして新設。
公開 API:
    StockQuote      … 1 銘柄のスナップショット
    StockFetcher    … 株価取得 (yfinance)
    evaluate_alerts … 条件評価 (純粋関数)
    LineNotifier    … LINE Messaging API への push 送信
    load_stock_config / run_once … 設定読み込みと一括実行
"""
from stocks.models import StockQuote
from stocks.alerts import AlertHit, evaluate_alerts
from stocks.analyst import StockAnalyst, BoardStockAnalyst, build_agenda
from stocks.fetcher import StockFetcher
from stocks.line_notifier import LineNotifier
from stocks.state import AlertStateStore, hit_key
from stocks.config import (
    StockConfig,
    WatchItem,
    AlertCondition,
    LineConfig,
    BoardConfig,
    load_stock_config,
)
from stocks.runner import run_once

__all__ = [
    "StockQuote",
    "AlertHit",
    "evaluate_alerts",
    "StockAnalyst",
    "BoardStockAnalyst",
    "build_agenda",
    "StockFetcher",
    "LineNotifier",
    "AlertStateStore",
    "hit_key",
    "StockConfig",
    "WatchItem",
    "AlertCondition",
    "LineConfig",
    "BoardConfig",
    "load_stock_config",
    "run_once",
]
