from .base import ALWAYS_INCLUDE, MemoryEntry, MemoryStore


class LettaMemoryStore(MemoryStore):
    """
    Letta サーバーをバックエンドにする実装（要: 稼働中の Letta サーバー）。
    カテゴリは "[カテゴリ] 本文" の接頭辞としてアーカイバル記憶に格納する。
    """

    def __init__(self, base_url: str, agent_id: str):
        from letta_client import Letta  # 遅延import: letta-client未導入環境を壊さない
        self._client = Letta(base_url=base_url)
        self._agent_id = agent_id

    def remember(self, entry: MemoryEntry) -> None:
        self._client.agents.passages.create(
            agent_id=self._agent_id,
            text=f"[{entry.category} | {entry.timestamp}] {entry.content}",
        )

    def entries(self, category: str | None = None) -> list[MemoryEntry]:
        passages = self._client.agents.passages.list(agent_id=self._agent_id)
        result = []
        for p in passages:
            text = p.text or ""
            cat, ts, content = _parse(text)
            if category is None or cat == category:
                result.append(MemoryEntry(category=cat, content=content, timestamp=ts))
        return result

    def load_context(self, query: str, top_k: int = 5) -> str:
        always = [
            e for c in ALWAYS_INCLUDE for e in self.entries(category=c)
        ]
        searched = self._client.agents.passages.list(
            agent_id=self._agent_id, search=query, limit=top_k
        )
        lines = [f"[{e.category} | {e.timestamp}] {e.content}" for e in always]
        seen = set(lines)
        for p in searched:
            t = p.text or ""
            if t not in seen:
                lines.append(t)
                seen.add(t)
        return "\n".join(lines)


def _parse(text: str) -> tuple[str, str, str]:
    if text.startswith("[") and "]" in text:
        head, _, content = text.partition("]")
        head = head[1:]
        cat, _, ts = head.partition(" | ")
        return cat.strip(), ts.strip(), content.strip()
    return "過去意思決定", "", text
