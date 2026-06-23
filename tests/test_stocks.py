"""株価通知モジュールのテスト (ネットワーク非依存)。"""
import pytest

from stocks.alerts import evaluate_alerts
from stocks.analyst import build_agenda
from stocks.config import (
    AlertCondition,
    LineConfig,
    StockConfig,
    WatchItem,
    load_stock_config,
)
from stocks.line_notifier import LineNotifier, LineNotifyError
from stocks.models import StockQuote
from stocks.runner import build_message, run_once


# ── モデル ──────────────────────────────────────────────────────────────────

def test_quote_change_and_pct():
    q = StockQuote(symbol="AAPL", name="Apple", price=110.0, previous_close=100.0, currency="USD")
    assert q.change == pytest.approx(10.0)
    assert q.change_pct == pytest.approx(10.0)


def test_quote_pct_zero_previous_close():
    q = StockQuote(symbol="X", name="X", price=10.0, previous_close=0.0)
    assert q.change_pct == 0.0


# ── アラート評価 ──────────────────────────────────────────────────────────────

def _quote(price, prev):
    return StockQuote(symbol="7203.T", name="トヨタ", price=price, previous_close=prev, currency="JPY")


def test_price_above_fires():
    hits = evaluate_alerts(_quote(3600, 3500), [AlertCondition(type="price_above", value=3500)])
    assert len(hits) == 1


def test_price_below_not_fire():
    hits = evaluate_alerts(_quote(3600, 3500), [AlertCondition(type="price_below", value=2500)])
    assert hits == []


def test_change_pct_below_fires_on_drop():
    hits = evaluate_alerts(_quote(2900, 3000), [AlertCondition(type="change_pct_below", value=-3)])
    assert len(hits) == 1


def test_multiple_conditions():
    conds = [
        AlertCondition(type="price_above", value=2000),
        AlertCondition(type="change_pct_above", value=1),
    ]
    hits = evaluate_alerts(_quote(2100, 2000), conds)
    assert len(hits) == 2


def test_unknown_condition_raises():
    with pytest.raises(ValueError):
        evaluate_alerts(_quote(100, 100), [AlertCondition(type="bogus", value=1)])


# ── runner ────────────────────────────────────────────────────────────────

class FakeFetcher:
    def __init__(self, quotes):
        self._quotes = {q.symbol: q for q in quotes}

    def fetch(self, symbol, name=None):
        return self._quotes[symbol]


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def push(self, text):
        self.sent.append(text)


def test_run_once_notifies_on_hit():
    cfg = StockConfig(watchlist=[
        WatchItem(symbol="AAPL", name="Apple",
                  conditions=[AlertCondition(type="price_below", value=200)]),
    ])
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])
    notifier = FakeNotifier()

    result = run_once(cfg, fetcher=fetcher, notifier=notifier)

    assert result.notified is True
    assert len(notifier.sent) == 1
    assert "Apple" in notifier.sent[0]


def test_run_once_no_hit_no_notify():
    cfg = StockConfig(watchlist=[
        WatchItem(symbol="AAPL", conditions=[AlertCondition(type="price_above", value=999)]),
    ])
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])
    notifier = FakeNotifier()

    result = run_once(cfg, fetcher=fetcher, notifier=notifier)

    assert result.notified is False
    assert notifier.sent == []


def test_run_once_dry_run_builds_message_without_sending():
    cfg = StockConfig(watchlist=[
        WatchItem(symbol="AAPL", conditions=[AlertCondition(type="price_below", value=200)]),
    ])
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])

    result = run_once(cfg, fetcher=fetcher, dry_run=True)

    assert result.notified is False
    assert "Apple" in result.message


def test_build_message_groups_by_symbol():
    q = StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")
    hits = evaluate_alerts(q, [
        AlertCondition(type="price_below", value=200),
        AlertCondition(type="change_pct_below", value=-1),
    ])
    msg = build_message(hits)
    # ヘッダ (銘柄行) は 1 回だけ
    assert msg.count("Apple (AAPL)") == 1
    assert msg.count("条件成立") == 2


# ── 取締役会連携 (analyst) ────────────────────────────────────────────────────

class FakeAnalyst:
    def __init__(self, view="保有を推奨。下落は一時的と判断。", record=None):
        self.view = view
        self.calls = record if record is not None else []

    def analyze(self, quote, hits):
        self.calls.append((quote.symbol, len(hits)))
        return self.view


def test_build_agenda_includes_symbol_and_triggers():
    q = StockQuote("7203.T", "トヨタ", 2400.0, 2500.0, "JPY")
    hits = evaluate_alerts(q, [AlertCondition(type="change_pct_below", value=-3)])
    agenda = build_agenda(q, hits)
    assert "7203.T" in agenda
    assert "トヨタ" in agenda
    assert "前日比" in agenda


def test_run_once_with_analyst_adds_view_to_message():
    cfg = StockConfig(watchlist=[
        WatchItem(symbol="AAPL", name="Apple",
                  conditions=[AlertCondition(type="price_below", value=200)]),
    ])
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])
    notifier = FakeNotifier()
    analyst = FakeAnalyst(view="押し目買いを検討。")

    result = run_once(cfg, fetcher=fetcher, notifier=notifier, analyst=analyst)

    assert result.analyses["AAPL"] == "押し目買いを検討。"
    assert "取締役会の見解" in notifier.sent[0]
    assert "押し目買いを検討。" in notifier.sent[0]
    assert analyst.calls == [("AAPL", 1)]


def test_run_once_analyst_failure_still_notifies():
    class BoomAnalyst:
        def analyze(self, quote, hits):
            raise RuntimeError("LLM down")

    cfg = StockConfig(watchlist=[
        WatchItem(symbol="AAPL", conditions=[AlertCondition(type="price_below", value=200)]),
    ])
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])
    notifier = FakeNotifier()

    result = run_once(cfg, fetcher=fetcher, notifier=notifier, analyst=BoomAnalyst())

    assert result.notified is True            # 取締役会が落ちてもアラートは送る
    assert result.analyses == {}
    assert any("取締役会議論に失敗" in e for e in result.errors)


# ── LINE notifier ────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._response


def test_line_notifier_requires_token():
    with pytest.raises(LineNotifyError):
        LineNotifier(token="", to="U123")


def test_line_notifier_requires_to():
    with pytest.raises(LineNotifyError):
        LineNotifier(token="tok", to="")


def test_line_notifier_push_ok():
    session = FakeSession(FakeResponse(200))
    notifier = LineNotifier(token="tok", to="U123", session=session)
    notifier.push("hello")
    assert session.calls[0]["url"] == LineNotifier.PUSH_URL
    assert session.calls[0]["json"]["to"] == "U123"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_line_notifier_push_error_raises():
    session = FakeSession(FakeResponse(401, "invalid token"))
    notifier = LineNotifier(token="tok", to="U123", session=session)
    with pytest.raises(LineNotifyError):
        notifier.push("hello")


# ── config 読み込み ──────────────────────────────────────────────────────────

def test_load_stock_config_missing_returns_default(tmp_path):
    cfg = load_stock_config(str(tmp_path / "nope.yaml"))
    assert cfg.watchlist == []


def test_load_stock_config_parses(tmp_path):
    p = tmp_path / "stocks.yaml"
    p.write_text(
        "line:\n  to: U999\n"
        "watchlist:\n"
        "  - symbol: '7203.T'\n"
        "    name: トヨタ\n"
        "    conditions:\n"
        "      - type: price_above\n"
        "        value: 3000\n",
        encoding="utf-8",
    )
    cfg = load_stock_config(str(p))
    assert cfg.line.to == "U999"
    assert cfg.watchlist[0].symbol == "7203.T"
    assert cfg.watchlist[0].conditions[0].type == "price_above"


def test_line_config_env_fallback(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "envtok")
    monkeypatch.setenv("LINE_TO", "envto")
    lc = LineConfig()
    assert lc.resolved_token() == "envtok"
    assert lc.resolved_to() == "envto"
