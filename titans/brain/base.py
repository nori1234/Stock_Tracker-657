from abc import ABC, abstractmethod
from crewai import LLM


class BrainProvider(ABC):
    """
    脳は1つだけ原則 — One Brain Principle.
    All agents share the single LLM object returned by get_llm().
    """

    @abstractmethod
    def get_llm(self) -> LLM:
        """Return the single shared LLM instance (cached after first call)."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Verify the underlying model server is reachable."""
        ...

    @abstractmethod
    def model_info(self) -> dict:
        """Return model metadata: name, size, context_length."""
        ...
