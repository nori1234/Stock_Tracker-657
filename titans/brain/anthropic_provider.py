import os

from crewai import LLM

from .base import BrainProvider


class AnthropicProvider(BrainProvider):
    """
    Anthropic API をバックエンドにする BrainProvider。
    ANTHROPIC_API_KEY 環境変数（.env 可）が必要。
    Ollama が使えない環境（モデルレジストリ遮断など）での実行経路。
    """

    def __init__(self, model: str, temperature: float, timeout: int):
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._llm_instance: LLM | None = None

    def get_llm(self) -> LLM:
        if self._llm_instance is None:
            self._llm_instance = LLM(
                model=f"anthropic/{self._model}",
                temperature=self._temperature,
                timeout=self._timeout,
            )
        return self._llm_instance

    def health_check(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def model_info(self) -> dict:
        return {
            "name": self._model,
            "provider": "anthropic",
            "api_key_set": self.health_check(),
        }
