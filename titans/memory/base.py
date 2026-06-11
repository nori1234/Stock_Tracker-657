from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

# 設計書の保存対象カテゴリ。PDF本文・契約書全文などは保存しない(それらはQdrantへ)。
CATEGORIES = ["ユーザー嗜好", "経営方針", "過去意思決定", "禁止事項", "顧客情報"]

# 関連度に関わらず毎回コンテキストに含めるカテゴリ
ALWAYS_INCLUDE = ("禁止事項", "経営方針")


@dataclass
class MemoryEntry:
    category: str
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M")
    )


class MemoryStore(ABC):
    """Long-Term Memory の抽象。Letta / ローカルJSON を差し替え可能にする。"""

    @abstractmethod
    def remember(self, entry: MemoryEntry) -> None:
        ...

    @abstractmethod
    def entries(self, category: str | None = None) -> list[MemoryEntry]:
        ...

    @abstractmethod
    def load_context(self, query: str, top_k: int = 5) -> str:
        """
        ContextComponents.long_term_memory に渡す整形済みテキストを返す。
        禁止事項・経営方針は常に含め、他カテゴリは query との関連度順に top_k 件。
        """
        ...

    def count(self) -> int:
        return len(self.entries())
