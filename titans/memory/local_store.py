import json
from dataclasses import asdict
from pathlib import Path

from titans.retrieval.base import tokenize

from .base import ALWAYS_INCLUDE, MemoryEntry, MemoryStore


class LocalMemoryStore(MemoryStore):
    """
    JSONファイル永続化のオフライン実装。Lettaサーバー不要で全機能が動く。
    Phase 3 の既定。Lettaへ移行しても MemoryStore 契約は同一。
    """

    def __init__(self, storage_dir: str):
        self._path = Path(storage_dir) / "memory.json"
        self._entries: list[MemoryEntry] = []
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = [MemoryEntry(**e) for e in raw]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def remember(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)
        self._save()

    def entries(self, category: str | None = None) -> list[MemoryEntry]:
        if category is None:
            return list(self._entries)
        return [e for e in self._entries if e.category == category]

    def load_context(self, query: str, top_k: int = 5) -> str:
        always = [e for e in self._entries if e.category in ALWAYS_INCLUDE]
        rest = [e for e in self._entries if e.category not in ALWAYS_INCLUDE]

        # 1文字トークンは偶然一致のノイズ源になるため関連度計算から除外
        q_tokens = {t for t in tokenize(query) if len(t) >= 2}

        def relevance(e: MemoryEntry) -> int:
            return len(q_tokens & {t for t in tokenize(e.content) if len(t) >= 2})

        relevant = sorted(rest, key=relevance, reverse=True)
        relevant = [e for e in relevant[:top_k] if relevance(e) > 0]

        selected = always + relevant
        if not selected:
            return ""
        return "\n".join(f"[{e.category} | {e.timestamp}] {e.content}" for e in selected)
