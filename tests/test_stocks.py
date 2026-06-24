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
from stocks.runner import build_error_message, build_message, run_once


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


# ── 追加のアラート条件 (フェーズC) ────────────────────────────────────────────

def test_ma_conditions_without_value():
    q = StockQuote("AAPL", "Apple", 190.0, 188.0, "USD", ma50=180.0, ma200=200.0)
    hits = evaluate_alerts(q, [
        AlertCondition(type="above_ma50"),   # 190 >= 180 → 発火
        AlertCondition(type="below_ma200"),  # 190 <= 200 → 発火
        AlertCondition(type="above_ma200"),  # 190 >= 200 → 不発火
    ])
    msgs = [h.message for h in hits]
    assert any("50日移動平均を上回る" in m for m in msgs)
    assert any("200日移動平均を下回る" in m for m in msgs)
    assert len(hits) == 2


def test_ma_condition_missing_data_does_not_fire():
    q = StockQuote("AAPL", "Apple", 190.0, 188.0, "USD")  # ma50 未取得
    hits = evaluate_alerts(q, [AlertCondition(type="above_ma50")])
    assert hits == []


def test_volume_and_year_high_conditions():
    q = StockQuote("AAPL", "Apple", 198.0, 190.0, "USD", volume=5_000_000, year_high=200.0)
    hits = evaluate_alerts(q, [
        AlertCondition(type="volume_above", value=1_000_000),  # 発火
        AlertCondition(type="near_year_high", value=2),        # 200*0.98=196 <= 198 → 発火
    ])
    assert len(hits) == 2


def test_value_required_condition_raises_without_value():
    q = StockQuote("AAPL", "Apple", 100.0, 100.0)
    with pytest.raises(ValueError):
        evaluate_alerts(q, [AlertCondition(type="price_above")])


# ── runner ────────────────────────────────────────────────────────────────

class FakeFetcher:
    def __init__(self, quotes):
        self._quotes = {q.symbol: q for q in quotes}

    def fetch(self, symbol, name=None):
        return self._quotes[symbol]


class FakeNotifier:
    def __init__(self):
        self.sent = []
        self.flex = []

    def push(self, text):
        self.sent.append(text)

    def push_flex(self, alt_text, contents):
        self.flex.append((alt_text, contents))


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


# ── 重複抑制 (state store) ───────────────────────────────────────────────────

from stocks.state import AlertStateStore, hit_key


def _cfg_aapl_below_200():
    return StockConfig(watchlist=[
        WatchItem(symbol="AAPL", name="Apple",
                  conditions=[AlertCondition(type="price_below", value=200)]),
    ])


def test_dedup_suppresses_second_run(tmp_path):
    cfg = _cfg_aapl_below_200()
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])
    state_path = str(tmp_path / "state.json")

    # 1 回目: 新規成立 → 通知される
    n1 = FakeNotifier()
    r1 = run_once(cfg, fetcher=fetcher, notifier=n1, state_store=AlertStateStore(state_path))
    assert r1.notified is True
    assert len(n1.sent) == 1

    # 2 回目: 同じ条件が成立し続けている → 抑制され通知されない
    n2 = FakeNotifier()
    r2 = run_once(cfg, fetcher=fetcher, notifier=n2, state_store=AlertStateStore(state_path))
    assert r2.notified is False
    assert n2.sent == []
    assert r2.suppressed == 1


def test_dedup_rearms_after_condition_clears(tmp_path):
    cfg = _cfg_aapl_below_200()
    state_path = str(tmp_path / "state.json")

    # 1 回目: 150 < 200 で成立 → 通知
    n1 = FakeNotifier()
    run_once(cfg, fetcher=FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")]),
             notifier=n1, state_store=AlertStateStore(state_path))
    assert len(n1.sent) == 1

    # 2 回目: 250 で条件外れる → 通知なし、状態は再武装
    n2 = FakeNotifier()
    run_once(cfg, fetcher=FakeFetcher([StockQuote("AAPL", "Apple", 250.0, 240.0, "USD")]),
             notifier=n2, state_store=AlertStateStore(state_path))
    assert n2.sent == []

    # 3 回目: 再び 150 < 200 → 再武装済みなので再通知される
    n3 = FakeNotifier()
    r3 = run_once(cfg, fetcher=FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")]),
                  notifier=n3, state_store=AlertStateStore(state_path))
    assert r3.notified is True
    assert len(n3.sent) == 1


def test_dedup_dry_run_does_not_persist(tmp_path):
    cfg = _cfg_aapl_below_200()
    state_path = str(tmp_path / "state.json")
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])

    run_once(cfg, fetcher=fetcher, state_store=AlertStateStore(state_path), dry_run=True)

    # dry-run では状態ファイルを書かない → 次の本番実行でちゃんと通知される
    n = FakeNotifier()
    r = run_once(cfg, fetcher=fetcher, notifier=n, state_store=AlertStateStore(state_path))
    assert r.notified is True
    assert len(n.sent) == 1


def test_state_store_handles_corrupt_file(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not valid json{", encoding="utf-8")
    store = AlertStateStore(str(p))
    assert store.active == set()


def test_hit_key_stable():
    q = StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")
    hits = evaluate_alerts(q, [AlertCondition(type="price_below", value=200)])
    assert hit_key(hits[0]) == "AAPL|price_below|200.0"


# ── クールダウン (時間ベース抑制) ────────────────────────────────────────────

from datetime import datetime, timedelta

from stocks.state import hit_key as _hit_key


def test_cooldown_suppresses_quick_refire(tmp_path):
    """エッジ的には新規でも、最後の通知から cooldown 内なら抑制する。"""
    cfg = _cfg_aapl_below_200()
    state_path = str(tmp_path / "state.json")

    # 1回目: 成立 → 通知 (last_notified 記録)
    n1 = FakeNotifier()
    r1 = run_once(cfg, fetcher=FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")]),
                  notifier=n1, state_store=AlertStateStore(state_path), cooldown_minutes=60)
    assert r1.notified is True

    # 条件が外れて再武装 (active から消える)
    run_once(cfg, fetcher=FakeFetcher([StockQuote("AAPL", "Apple", 250.0, 240.0, "USD")]),
             notifier=FakeNotifier(), state_store=AlertStateStore(state_path), cooldown_minutes=60)

    # すぐ再成立 → エッジ的には新規だが cooldown 60 分内なので抑制
    n3 = FakeNotifier()
    r3 = run_once(cfg, fetcher=FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")]),
                  notifier=n3, state_store=AlertStateStore(state_path), cooldown_minutes=60)
    assert r3.notified is False
    assert n3.sent == []
    assert r3.suppressed == 1


def test_cooldown_allows_after_window(tmp_path):
    state_path = str(tmp_path / "state.json")
    store = AlertStateStore(state_path)
    key = "AAPL|price_below|200.0"
    now = datetime(2026, 1, 1, 12, 0, 0)

    # 70 分前に通知済みとして記録
    store.commit({key}, notified_keys=[key], now=now - timedelta(minutes=70))
    reloaded = AlertStateStore(state_path)

    assert reloaded.cooled_down(key, now, cooldown_minutes=60) is True   # 60分窓は過ぎた
    assert reloaded.cooled_down(key, now, cooldown_minutes=90) is False  # 90分窓内


def test_cooldown_disabled_when_zero(tmp_path):
    store = AlertStateStore(str(tmp_path / "s.json"))
    assert store.cooled_down("k", datetime.now(), cooldown_minutes=0) is True


# ── 取得失敗の通知 (notify_errors) ───────────────────────────────────────────

class BoomFetcher:
    def fetch(self, symbol, name=None):
        from stocks.fetcher import StockFetchError
        raise StockFetchError("取得不能")


def test_notify_errors_sends_failure_message():
    cfg = StockConfig(watchlist=[WatchItem(symbol="AAPL", conditions=[])])
    notifier = FakeNotifier()
    result = run_once(cfg, fetcher=BoomFetcher(), notifier=notifier, notify_errors=True)
    assert result.error_notified is True
    assert len(notifier.sent) == 1
    assert "取得エラー" in notifier.sent[0]
    assert "AAPL" in notifier.sent[0]


def test_no_notify_errors_by_default():
    cfg = StockConfig(watchlist=[WatchItem(symbol="AAPL", conditions=[])])
    notifier = FakeNotifier()
    result = run_once(cfg, fetcher=BoomFetcher(), notifier=notifier)
    assert result.error_notified is False
    assert notifier.sent == []


def test_build_error_message_truncates():
    msg = build_error_message([f"S{i}: boom" for i in range(25)])
    assert "ほか 5 件" in msg


# ── fetcher (yfinance をモック) ───────────────────────────────────────────────

import sys
import types


class _FakeFastInfo(dict):
    """fast_info 風 (dict アクセス)。"""


class _FakeTicker:
    def __init__(self, fast=None, info=None):
        self.fast_info = fast
        self._info = info or {}

    @property
    def info(self):
        return self._info


def _install_fake_yfinance(monkeypatch, ticker):
    fake = types.ModuleType("yfinance")
    fake.Ticker = lambda symbol: ticker
    monkeypatch.setitem(sys.modules, "yfinance", fake)


def test_fetcher_uses_fast_info(monkeypatch):
    from stocks.fetcher import StockFetcher

    ticker = _FakeTicker(fast=_FakeFastInfo(
        last_price=2500.0, previous_close=2400.0, currency="JPY"))
    _install_fake_yfinance(monkeypatch, ticker)

    q = StockFetcher().fetch("7203.T", name="トヨタ")
    assert q.price == 2500.0
    assert q.previous_close == 2400.0
    assert q.currency == "JPY"
    assert q.name == "トヨタ"
    assert q.change_pct > 0


def test_fetcher_falls_back_to_info(monkeypatch):
    from stocks.fetcher import StockFetcher

    # fast_info は欠損、.info から取得
    ticker = _FakeTicker(fast=_FakeFastInfo(), info={
        "regularMarketPrice": 190.0,
        "regularMarketPreviousClose": 200.0,
        "currency": "USD",
        "shortName": "Apple Inc.",
    })
    _install_fake_yfinance(monkeypatch, ticker)

    q = StockFetcher().fetch("AAPL")
    assert q.price == 190.0
    assert q.previous_close == 200.0
    assert q.name == "Apple Inc."


def test_fetcher_raises_when_no_data(monkeypatch):
    from stocks.fetcher import StockFetcher, StockFetchError

    ticker = _FakeTicker(fast=_FakeFastInfo(), info={})
    _install_fake_yfinance(monkeypatch, ticker)

    with pytest.raises(StockFetchError):
        StockFetcher().fetch("BOGUS")


# ── Flex Message (フェーズC) ─────────────────────────────────────────────────

from stocks.flex import alt_text as flex_alt, build_flex


def test_build_flex_single_symbol_is_bubble():
    q = StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")
    hits = evaluate_alerts(q, [AlertCondition(type="price_below", value=200)])
    contents = build_flex(hits)
    assert contents["type"] == "bubble"
    assert contents["header"]["contents"][0]["text"] == "Apple"


def test_build_flex_multi_symbol_is_carousel():
    q1 = StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")
    q2 = StockQuote("7203.T", "トヨタ", 2400.0, 2500.0, "JPY")
    hits = (evaluate_alerts(q1, [AlertCondition(type="price_below", value=200)]) +
            evaluate_alerts(q2, [AlertCondition(type="price_below", value=2500)]))
    contents = build_flex(hits)
    assert contents["type"] == "carousel"
    assert len(contents["contents"]) == 2


def test_run_once_use_flex_calls_push_flex():
    cfg = StockConfig(watchlist=[
        WatchItem(symbol="AAPL", name="Apple",
                  conditions=[AlertCondition(type="price_below", value=200)]),
    ])
    fetcher = FakeFetcher([StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")])
    notifier = FakeNotifier()

    result = run_once(cfg, fetcher=fetcher, notifier=notifier, use_flex=True)

    assert result.notified is True
    assert len(notifier.flex) == 1          # flex で送信
    assert notifier.sent == []              # text では送らない
    assert "AAPL" in notifier.flex[0][0]    # altText


def test_flex_alt_text_lists_symbols():
    q = StockQuote("AAPL", "Apple", 150.0, 160.0, "USD")
    hits = evaluate_alerts(q, [AlertCondition(type="price_below", value=200)])
    assert "AAPL" in flex_alt(hits)


# ── 取締役会の一言サマリ (フェーズC) ──────────────────────────────────────────

from stocks.analyst import summarize_conclusion


def test_summarize_conclusion_takes_first_sentence():
    text = "## 結論\n- 保有を継続すべきである。理由は以下の通り。\n詳細..."
    s = summarize_conclusion(text)
    assert s == "保有を継続すべきである。"


def test_summarize_conclusion_truncates_long():
    s = summarize_conclusion("あ" * 300, max_chars=100)
    assert s.endswith("…")
    assert len(s) <= 101


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


def test_board_config_defaults_disabled():
    cfg = StockConfig()
    assert cfg.board.enabled is False
    assert cfg.board.titans_config == "config.yaml"


def test_load_stock_config_parses_board(tmp_path):
    p = tmp_path / "stocks.yaml"
    p.write_text(
        "board:\n"
        "  enabled: true\n"
        "  summary: true\n"
        "  provider: anthropic\n"
        "  model: claude-haiku-4-5-20251001\n"
        "watchlist: []\n",
        encoding="utf-8",
    )
    cfg = load_stock_config(str(p))
    assert cfg.board.enabled is True
    assert cfg.board.summary is True
    assert cfg.board.provider == "anthropic"
    assert cfg.board.model == "claude-haiku-4-5-20251001"


def test_line_config_env_fallback(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "envtok")
    monkeypatch.setenv("LINE_TO", "envto")
    lc = LineConfig()
    assert lc.resolved_token() == "envtok"
    assert lc.resolved_to() == "envto"
