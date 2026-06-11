import pytest
from titans.brain.stub_provider import StubProvider
from titans.brain.openai_compatible_provider import OpenAICompatibleProvider
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


# --- Phase 5: OpenAI互換 (TTT-Mamba / vLLM 等) Provider ---

def test_openai_compatible_singleton_and_model_prefix():
    p = OpenAICompatibleProvider(
        model="ttt-mamba-3b", base_url="http://localhost:18999/v1",
        temperature=0.3, timeout=10,
    )
    llm1 = p.get_llm()
    llm2 = p.get_llm()
    assert llm1 is llm2                          # 脳は1つ（同一インスタンス）
    # hosted_vllm 接頭辞は provider ルーティングに消費され、OpenAI互換
    # クライアントへ解決される（モデル名自体はベア名で保持される）
    assert type(llm1).__name__ == "OpenAICompatibleCompletion"
    assert llm1.model == "ttt-mamba-3b"


def test_openai_compatible_health_check_graceful_without_server():
    p = OpenAICompatibleProvider(
        model="x", base_url="http://localhost:18999/v1", temperature=0.0, timeout=2,
    )
    # サーバー無しでも例外で落ちず False を返す
    assert p.health_check() is False
    info = p.model_info()
    assert info["provider"] == "openai_compatible"
    assert info["reachable"] is False


def test_openai_compatible_default_api_key(monkeypatch):
    monkeypatch.delenv("TITANS_LLM_API_KEY", raising=False)
    p = OpenAICompatibleProvider(
        model="x", base_url="http://localhost:1/v1", temperature=0.0, timeout=1,
    )
    assert p._api_key == "not-needed"


def test_create_brain_provider_openai_compatible():
    config = AppConfig(brain=BrainConfig(
        provider="openai_compatible", model="ttt-mamba-3b",
        base_url="http://localhost:8000/v1",
    ))
    provider = create_brain_provider(config)
    assert isinstance(provider, OpenAICompatibleProvider)
