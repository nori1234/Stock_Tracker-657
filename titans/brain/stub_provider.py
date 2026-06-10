from crewai import LLM
from .base import BrainProvider


class StubProvider(BrainProvider):
    """No-op provider for dry-run testing without Ollama running."""

    def get_llm(self) -> LLM:
        return LLM(
            model="ollama/stub",
            base_url="http://localhost:99999",
            temperature=0.0,
        )

    def health_check(self) -> bool:
        return False

    def model_info(self) -> dict:
        return {"name": "stub", "status": "stub"}
