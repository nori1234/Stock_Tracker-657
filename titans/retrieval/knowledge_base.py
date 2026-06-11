from .base import RetrievedChunk
from .bm25_store import BM25Retriever
from .embedder import create_embedder
from .graph_store import GraphRetriever
from .ingest import load_directory
from .merger import reciprocal_rank_fusion
from .qdrant_store import QdrantRetriever


class KnowledgeBase:
    """
    Retrieval Layer のファサード。
    STEP1 Qdrant(意味) + STEP2 GraphRAG(関係性) + STEP3 BM25(キーワード)
    → RRF統合 (knowledge = merge(qdrant_result, graph_result, bm25_result))。
    """

    def __init__(
        self,
        storage_dir: str,
        embedder_kind: str = "hashing",
        embedding_dim: int = 512,
        ollama_base_url: str = "http://localhost:11434",
        graph_enabled: bool = True,
        graph_max_hops: int = 2,
    ):
        embedder = create_embedder(embedder_kind, embedding_dim, ollama_base_url)
        self._qdrant = QdrantRetriever(f"{storage_dir}/qdrant", embedder)
        self._bm25 = BM25Retriever(storage_dir)
        self._retrievers = [self._qdrant, self._bm25]
        if graph_enabled:
            self._graph = GraphRetriever(storage_dir, max_hops=graph_max_hops)
            self._retrievers.append(self._graph)

    def ingest_directory(self, directory: str) -> int:
        chunks = load_directory(directory)
        for r in self._retrievers:
            r.add(chunks)
        return len(chunks)

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        results = [r.search(query, top_k=top_k * 2) for r in self._retrievers]
        return reciprocal_rank_fusion(results, top_k=top_k)

    def retrieve_as_text(self, query: str, top_k: int = 4) -> str:
        """ContextComponents.retrieved_knowledge に渡す整形済みテキスト。"""
        chunks = self.retrieve(query, top_k=top_k)
        if not chunks:
            return ""
        return "\n\n".join(f"[出典: {c.source}]\n{c.text}" for c in chunks)

    def count(self) -> dict[str, int]:
        counts = {"qdrant": self._qdrant.count(), "bm25": self._bm25.count()}
        if hasattr(self, "_graph"):
            counts["graph"] = self._graph.count()
        return counts

    def close(self) -> None:
        self._qdrant.close()
