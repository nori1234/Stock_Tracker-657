from .base import CATEGORIES, MemoryEntry, MemoryStore
from .local_store import LocalMemoryStore

__all__ = ["CATEGORIES", "MemoryEntry", "MemoryStore", "LocalMemoryStore", "create_memory_store"]


def create_memory_store(config) -> MemoryStore:
    """config.memory.provider に応じた MemoryStore を返すファクトリ。"""
    if config.memory.provider == "local":
        return LocalMemoryStore(storage_dir=config.memory.storage_dir)
    if config.memory.provider == "letta":
        from .letta_store import LettaMemoryStore
        return LettaMemoryStore(
            base_url=config.memory.letta_base_url,
            agent_id=config.memory.letta_agent_id,
        )
    raise ValueError(f"Unknown memory provider: {config.memory.provider}")
