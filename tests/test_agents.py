import pytest
from titans.brain.stub_provider import StubProvider
from titans.agents.board_agents import create_board_agents
from titans.utils.config_loader import AppConfig


@pytest.fixture
def shared_llm():
    provider = StubProvider()
    return provider.get_llm()


@pytest.fixture
def config():
    return AppConfig()


def test_all_agents_created(shared_llm, config):
    agents = create_board_agents(shared_llm, config)
    assert set(agents.keys()) == {"cfo", "clo", "ceo", "auditor"}


def test_one_brain_principle(shared_llm, config):
    """All agents must share the SAME LLM object."""
    agents = create_board_agents(shared_llm, config)
    assert agents["cfo"].llm is agents["clo"].llm
    assert agents["clo"].llm is agents["ceo"].llm
    assert agents["ceo"].llm is agents["auditor"].llm


def test_agent_roles_are_japanese(shared_llm, config):
    agents = create_board_agents(shared_llm, config)
    for name, agent in agents.items():
        assert len(agent.role) > 0, f"{name} role is empty"
        assert agent.role != name, f"{name} role should be a Japanese title, not '{name}'"


def test_no_delegation(shared_llm, config):
    agents = create_board_agents(shared_llm, config)
    for agent in agents.values():
        assert agent.allow_delegation is False
