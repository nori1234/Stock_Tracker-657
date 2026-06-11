import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .base import RetrievedChunk, Retriever
from .embedder import Embedder

COLLECTION = "titans_knowledge"


class QdrantRetriever(Retriever):
    """
    STEP1: 意味検索（Qdrant ローカルモード — サーバープロセス不要）。
    """

    def __init__(self, storage_path: str, embedder: Embedder):
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=storage_path)
        self._embedder = embedder
        if not self._client.collection_exists(COLLECTION):
            self._client.create_collection(
                COLLECTION,
                vectors_config=VectorParams(size=embedder.dim, distance=Distance.COSINE),
            )

    def add(self, chunks: list[RetrievedChunk]) -> None:
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=self._embedder.embed(c.text),
                payload={"text": c.text, "source": c.source},
            )
            for c in chunks
        ]
        if points:
            self._client.upsert(COLLECTION, points)

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        res = self._client.query_points(
            COLLECTION, query=self._embedder.embed(query), limit=top_k
        )
        return [
            RetrievedChunk(
                text=p.payload["text"], source=p.payload["source"], score=p.score
            )
            for p in res.points
        ]

    def count(self) -> int:
        return self._client.count(COLLECTION).count

    def close(self) -> None:
        self._client.close()
