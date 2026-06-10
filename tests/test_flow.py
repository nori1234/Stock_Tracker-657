import pytest
from titans.utils.context_builder import ContextComponents, build_task_description
from titans.brain.stub_provider import StubProvider
from titans.agents.board_agents import create_board_agents
from titans.tasks.board_tasks import create_board_tasks
from titans.utils.config_loader import AppConfig


def test_context_builder_includes_user_input():
    components = ContextComponents(
        user_input="テスト経営課題",
        task_description="テストタスク",
    )
    result = build_task_description(components)
    assert "テスト経営課題" in result
    assert "テストタスク" in result


def test_context_builder_skips_empty_ltm():
    components = ContextComponents(user_input="テスト", long_term_memory="")
    result = build_task_description(components)
    assert "長期記憶" not in result


def test_context_builder_skips_empty_knowledge():
    components = ContextComponents(user_input="テスト", retrieved_knowledge="")
    result = build_task_description(components)
    assert "関連知識" not in result


def test_context_builder_includes_ltm_when_set():
    components = ContextComponents(user_input="テスト", long_term_memory="過去の意思決定")
    result = build_task_description(components)
    assert "長期記憶" in result
    assert "過去の意思決定" in result


def test_five_tasks_created():
    provider = StubProvider()
    llm = provider.get_llm()
    config = AppConfig()
    agents = create_board_agents(llm, config)
    tasks = create_board_tasks(agents, "テスト経営課題")
    assert len(tasks) == 5


def test_task_context_chain():
    provider = StubProvider()
    llm = provider.get_llm()
    config = AppConfig()
    agents = create_board_agents(llm, config)
    tasks = create_board_tasks(agents, "テスト経営課題")

    task_cfo, task_clo, task_ceo_draft, task_auditor, task_ceo_final = tasks

    # CFO has no explicit context — downstream tasks do
    assert task_cfo in task_clo.context
    assert task_cfo in task_ceo_draft.context
    assert task_clo in task_ceo_draft.context
    assert task_cfo in task_auditor.context
    assert task_clo in task_auditor.context
    assert task_ceo_draft in task_auditor.context
    assert all(t in task_ceo_final.context for t in [task_cfo, task_clo, task_ceo_draft, task_auditor])
