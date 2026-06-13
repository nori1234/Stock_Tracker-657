from titans.memory.base import MemoryEntry
from titans.memory.local_store import LocalMemoryStore


def test_remember_and_persistence_roundtrip(tmp_path):
    s1 = LocalMemoryStore(str(tmp_path))
    s1.remember(MemoryEntry(category="経営方針", content="段階投資を原則とする"))
    s1.remember(MemoryEntry(category="禁止事項", content="競合他社への情報開示禁止"))
    s2 = LocalMemoryStore(str(tmp_path))
    assert s2.count() == 2
    assert s2.entries(category="禁止事項")[0].content == "競合他社への情報開示禁止"


def test_load_context_always_includes_policies_and_prohibitions(tmp_path):
    s = LocalMemoryStore(str(tmp_path))
    s.remember(MemoryEntry(category="禁止事項", content="ギャンブル関連事業への参入禁止"))
    s.remember(MemoryEntry(category="経営方針", content="ROI基準は3年15%"))
    s.remember(MemoryEntry(category="顧客情報", content="A社は決済が遅い"))
    # クエリと無関係でも禁止事項・経営方針は必ず含まれる
    ctx = s.load_context("全く関係ない宇宙開発の話")
    assert "ギャンブル" in ctx
    assert "ROI基準" in ctx
    assert "A社" not in ctx  # 無関連の顧客情報は含まれない


def test_load_context_relevance_filtering(tmp_path):
    s = LocalMemoryStore(str(tmp_path))
    s.remember(MemoryEntry(category="過去意思決定", content="医療SaaS事業はPMDA確認遅れで失敗した"))
    s.remember(MemoryEntry(category="過去意思決定", content="飲食店向けPOSは黒字化した"))
    ctx = s.load_context("医療診断支援サービスの投資判断")
    assert "医療SaaS" in ctx
    assert "POS" not in ctx


def test_load_context_empty_store_returns_empty(tmp_path):
    s = LocalMemoryStore(str(tmp_path))
    assert s.load_context("何か") == ""


def test_tasks_include_long_term_memory():
    from titans.agents.board_agents import create_board_agents
    from titans.brain.stub_provider import StubProvider
    from titans.tasks.board_tasks import create_board_tasks
    from titans.utils.config_loader import AppConfig

    agents = create_board_agents(StubProvider().get_llm(), AppConfig())
    tasks = create_board_tasks(
        agents, "テスト課題",
        long_term_memory="[禁止事項 | 2026-01-01] ギャンブル事業への参入禁止",
    )
    for t in tasks:
        assert "【長期記憶】" in t.description
        assert "ギャンブル" in t.description


def test_meeting_writes_back_decision(tmp_path, monkeypatch):
    """会議完了後に CEO 最終判断が「過去意思決定」として書き戻される。"""
    from crewai.llms.providers.openai.completion import OpenAICompletion
    monkeypatch.setattr(OpenAICompletion, "call",
                        lambda self, messages, *a, **k: "## 決定 段階投資で承認する")

    from titans.flows.board_meeting_flow import BoardMeetingFlow
    from titans.utils.config_loader import AppConfig, BrainConfig, create_brain_provider

    config = AppConfig(brain=BrainConfig(provider="stub"))
    config.retrieval.enabled = False
    store = LocalMemoryStore(str(tmp_path))
    store.remember(MemoryEntry(category="経営方針", content="ROI基準は3年15%"))

    flow = BoardMeetingFlow(
        brain_provider=create_brain_provider(config),
        config=config,
        memory_store=store,
    )
    flow.kickoff(inputs={"user_input": "新規事業の投資判断"})

    decisions = store.entries(category="過去意思決定")
    assert len(decisions) == 1
    assert "新規事業の投資判断" in decisions[0].content
    assert "段階投資で承認" in decisions[0].content
    # Memory Loader が会議プロンプト側にも届いている
    assert "ROI基準" in flow.state.long_term_memory
