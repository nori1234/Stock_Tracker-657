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

    type と、必要なら value を指定する:
        price_above / price_below            … 現在値 と value を比較
        change_pct_above / change_pct_below  … 前日比(%) と value を比較
        volume_above                         … 出来高 >= value
        near_year_high / near_year_low       … 52週高値/安値の value% 以内
        above_ma50 / below_ma50              … 現在値と50日移動平均を比較 (value不要)
        above_ma200 / below_ma200            … 現在値と200日移動平均を比較 (value不要)
    """

    type: str
    value: Optional[float] = None


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


class BoardConfig(BaseModel):
    """AI 取締役会 (titans) との融合設定。

    enabled=True にすると、アラート発火銘柄を CFO→CLO→CEO→監査役 が議論し、
    投資判断の結論を LINE 本文に添える。実 LLM (Ollama / Anthropic) が必要。
    CLI フラグ (--discuss 等) は、ここでの設定を上書きする。
    """

    enabled: bool = False
    summary: bool = False                  # 結論を一言サマリに短縮する
    provider: Optional[str] = None         # "anthropic" 等。None なら config.yaml の設定
    model: Optional[str] = None            # モデル上書き
    titans_config: str = "config.yaml"     # 取締役会の設定ファイル


class StockConfig(BaseModel):
    line: LineConfig = LineConfig()
    board: BoardConfig = BoardConfig()
    watchlist: List[WatchItem] = Field(default_factory=list)


def load_stock_config(config_path: str = "stocks.yaml") -> StockConfig:
    path = Path(config_path)
    if not path.exists():
        return StockConfig()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return StockConfig(**raw)
