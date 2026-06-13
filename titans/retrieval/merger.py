from .base import RetrievedChunk


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievedChunk]],
    top_k: int = 5,
    k: int = 60,
) -> list[RetrievedChunk]:
    """
    knowledge = merge(qdrant_result, bm25_result, ...) の実装。
    スコアの尺度が異なる検索器同士を順位ベース (RRF) で統合する。
    同一テキストは重複排除し、RRFスコアを合算する。
    """
    fused: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results):
            key = chunk.text
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in fused:
                fused[key] = chunk

    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)[:top_k]
    return [
        RetrievedChunk(text=t, source=fused[t].source, score=scores[t])
        for t in ranked
    ]
