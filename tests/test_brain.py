import pytest
from titans.brain.stub_provider import StubProvider
from titans.utils.config_loader import load_config, create_brain_provider, AppConfig, BrainConfig


def test_stub_provider_health_check_returns_false():
    provider = StubProvider()
    assert provider.health_check() is False


def test_stub_provider_model_info():
    provider = StubProvider()
    info = provider.model_info()
    assert info["name"] == "stub"


def test_create_brain_provider_stub():
    config = AppConfig(brain=BrainConfig(provider="stub"))
    provider = create_brain_provider(config)
    assert isinstance(provider, StubProvider)


def test_create_brain_provider_unknown_raises():
    config = AppConfig(brain=BrainConfig(provider="unknown_xyz"))
    with pytest.raises(ValueError, match="Unknown brain provider"):
        create_brain_provider(config)


def test_load_config_defaults_when_no_file():
    config = load_config("nonexistent_config_xyz.yaml")
    assert config.brain.provider == "ollama"
    assert config.brain.model == "qwen3:4b"
    assert config.meeting.max_iter == 3
