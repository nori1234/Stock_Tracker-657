import json
from pathlib import Path

from rank_bm25 import BM25Okapi

from .base import RetrievedChunk, Retriever, tokenize


class BM25Retriever(Retriever):
    """
    STEP3: キーワード検索（法律条文・会計科目・契約番号などの厳密一致に強い）。
    コーパスは JSON で永続化し、ロード時にインデックスを再構築する。
    """

    def __init__(self, storage_path: str):
        self._path = Path(storage_path) / "bm25_corpus.json"
        self._docs: list[dict] = []
        self._index: BM25Okapi | None = None
        if self._path.exists():
            self._docs = json.loads(self._path.read_text(encoding="utf-8"))
            self._rebuild()

    def _rebuild(self) -> None:
        if self._docs:
            self._index = BM25Okapi([tokenize(d["text"]) for d in self._docs])
        else:
            self._index = None

    def add(self, chunks: list[RetrievedChunk]) -> None:
        self._docs.extend({"text": c.text, "source": c.source} for c in chunks)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._docs, ensure_ascii=False), encoding="utf-8"
        )
        self._rebuild()

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if self._index is None:
            return []
        scores = self._index.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [
            RetrievedChunk(
                text=self._docs[i]["text"],
                source=self._docs[i]["source"],
                score=float(scores[i]),
            )
            for i in ranked[:top_k]
            if scores[i] > 0
        ]

    def count(self) -> int:
        return len(self._docs)
