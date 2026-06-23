"""株価通知の設定 (ウォッチリスト・アラート条件・LINE 送信先) を読み込む。

設定は ``stocks.yaml`` から読み込み、機密値 (アクセストークン・送信先) は
環境変数でも与えられる。優先順位は「YAML の明示値 > 環境変数」。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class AlertCondition(BaseModel):
    """1 つのアラート条件。

    type:
        price_above       … 現在値 >= value
        price_below       … 現在値 <= value
        change_pct_above  … 前日比(%) >= value
        change_pct_below  … 前日比(%) <= value
    """

    type: str
    value: float


class WatchItem(BaseModel):
    """監視する 1 銘柄とその条件。"""

    symbol: str                                  # yfinance 形式: 日本株 "7203.T" / 米国株 "AAPL"
    name: Optional[str] = None                   # 表示名 (省略時は取得値/シンボル)
    conditions: List[AlertCondition] = Field(default_factory=list)


class LineConfig(BaseModel):
    """LINE Messaging API の認証・送信先。

    LINE Notify は 2025-03 で終了したため Messaging API の push を使う。
    """

    channel_access_token: str = ""   # 空なら環境変数 LINE_CHANNEL_ACCESS_TOKEN
    to: str = ""                     # 送信先 userId/groupId。空なら環境変数 LINE_TO

    def resolved_token(self) -> str:
        return self.channel_access_token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

    def resolved_to(self) -> str:
        return self.to or os.environ.get("LINE_TO", "")


class StockConfig(BaseModel):
    line: LineConfig = LineConfig()
    watchlist: List[WatchItem] = Field(default_factory=list)


def load_stock_config(config_path: str = "stocks.yaml") -> StockConfig:
    path = Path(config_path)
    if not path.exists():
        return StockConfig()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return StockConfig(**raw)
