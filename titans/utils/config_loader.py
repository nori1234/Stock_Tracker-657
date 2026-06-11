import yaml
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class BrainConfig(BaseModel):
    provider: str = "ollama"
    model: str = "qwen3:4b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.3
    num_ctx: int = 8192
    timeout: int = 120


class RetrievalConfig(BaseModel):
    enabled: bool = True
    storage_dir: str = "./storage"
    top_k: int = 4
    embedder: str = "hashing"   # "hashing" (offline) | "ollama" (要 embedding モデル)
    embedding_dim: int = 512


class MeetingConfig(BaseModel):
    language: str = "ja"
    verbose: bool = False
    max_iter: int = 3


class OutputConfig(BaseModel):
    save_to_file: bool = True
    output_dir: str = "./outputs"


class AppConfig(BaseModel):
    brain: BrainConfig = BrainConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    meeting: MeetingConfig = MeetingConfig()
    output: OutputConfig = OutputConfig()


def load_config(config_path: str = "config.yaml") -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        return AppConfig()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig(**raw)


def create_brain_provider(config: AppConfig):
    """Factory returning the configured BrainProvider."""
    if config.brain.provider == "ollama":
        from titans.brain.ollama_provider import OllamaProvider
        return OllamaProvider(
            model=config.brain.model,
            base_url=config.brain.base_url,
            temperature=config.brain.temperature,
            num_ctx=config.brain.num_ctx,
            timeout=config.brain.timeout,
        )
    elif config.brain.provider == "anthropic":
        from titans.brain.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            model=config.brain.model,
            temperature=config.brain.temperature,
            timeout=config.brain.timeout,
        )
    elif config.brain.provider == "stub":
        from titans.brain.stub_provider import StubProvider
        return StubProvider()
    else:
        raise ValueError(f"Unknown brain provider: {config.brain.provider}")
