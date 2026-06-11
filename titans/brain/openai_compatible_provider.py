import os

from crewai import LLM

from .base import BrainProvider


class OpenAICompatibleProvider(BrainProvider):
    """
    任意の OpenAI 互換推論サーバーをバックエンドにする BrainProvider。

    Phase 5（共有SSM脳 / TTT-Mamba）の主要な接続経路。
    TTT-Mamba・Qwen・Gemma 等を vLLM / llama.cpp server / LM Studio などで
    配信すると OpenAI 互換 API になり、本 Provider がそのまま使える。

    GGUF を入手済みの場合は `ollama create` でローカル登録し
    OllamaProvider を使う方が手軽（README の Phase 5 を参照）。

    api_key はローカルサーバーでは不要なことが多いため、未設定時は
    ダミー値を送る（多くのサーバーは検証しない）。本物のキーが要る場合は
    .env の TITANS_LLM_API_KEY か config の api_key で指定する。
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        temperature: float,
        timeout: int,
        api_key: str = "",
    ):
        self._model = model
        self._base_url = base_url
        self._temperature = temperature
        self._timeout = timeout
        self._api_key = api_key or os.environ.get("TITANS_LLM_API_KEY") or "not-needed"
        self._llm_instance: LLM | None = None

    def get_llm(self) -> LLM:
        if self._llm_instance is None:
            # "hosted_vllm/" 接頭辞は任意のモデル名を受理し、litellm 不要で
            # crewai の OpenAI 互換クライアント(openai_compatible)に乗る。
            # base_url を自前サーバーに向けることで vLLM / llama.cpp server 等に接続する。
            self._llm_instance = LLM(
                model=f"hosted_vllm/{self._model}",
                base_url=self._base_url,
                api_key=self._api_key,
                temperature=self._temperature,
                timeout=self._timeout,
            )
        return self._llm_instance

    def health_check(self) -> bool:
        import urllib.request

        # OpenAI 互換サーバーは /v1/models を公開している
        url = self._base_url.rstrip("/")
        if not url.endswith("/v1"):
            url = f"{url}/v1"
        try:
            req = urllib.request.Request(
                f"{url}/models", headers={"Authorization": f"Bearer {self._api_key}"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def model_info(self) -> dict:
        return {
            "name": self._model,
            "provider": "openai_compatible",
            "base_url": self._base_url,
            "reachable": self.health_check(),
        }
