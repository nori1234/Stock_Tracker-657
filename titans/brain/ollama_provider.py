from crewai import LLM
from .base import BrainProvider


class OllamaProvider(BrainProvider):
    def __init__(
        self,
        model: str,
        base_url: str,
        temperature: float,
        num_ctx: int,
        max_tokens: int,
        timeout: int,
    ):
        self._model = model
        self._base_url = base_url
        self._temperature = temperature
        self._num_ctx = num_ctx
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._llm_instance: LLM | None = None

    def get_llm(self) -> LLM:
        if self._llm_instance is None:
            # crewai routes "ollama/*" through an OpenAI-compatible client, so
            # Ollama-specific options (e.g. num_ctx) must be passed via
            # extra_body["options"] — they are rejected as top-level kwargs.
            self._llm_instance = LLM(
                model=f"ollama/{self._model}",
                base_url=self._base_url,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                timeout=self._timeout,
                extra_body={"options": {
                    "num_ctx": self._num_ctx,
                    "num_predict": self._max_tokens,  # Ollama native output cap
                }},
            )
        return self._llm_instance

    def health_check(self) -> bool:
        try:
            import ollama as ollama_client
            client = ollama_client.Client(host=self._base_url)
            client.list()
            return True
        except Exception:
            return False

    def model_info(self) -> dict:
        try:
            import ollama as ollama_client
            client = ollama_client.Client(host=self._base_url)
            models = client.list()
            for m in models.models:
                if self._model in m.model:
                    return {
                        "name": m.model,
                        "size": m.size,
                        "modified": str(m.modified_at),
                    }
            return {"name": self._model, "status": "not_pulled"}
        except Exception as e:
            return {"name": self._model, "status": f"error: {e}"}
