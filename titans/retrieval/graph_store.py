import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .base import RetrievedChunk, Retriever, tokenize

# 知識ファイル内の関係記法: 「顧客A -[契約]-> 契約B」
TRIPLE_PATTERN = re.compile(r"^\s*(.+?)\s*-\[(.+?)\]->\s*(.+?)\s*$")


@dataclass(frozen=True)
class Edge:
    subject: str
    relation: str
    object: str
    source: str


def parse_triples(text: str, source: str) -> list[Edge]:
    """チャンクテキストから関係トリプル行を抽出する。通常の文は無視される。"""
    edges = []
    for line in text.splitlines():
        m = TRIPLE_PATTERN.match(line)
        if m:
            edges.append(Edge(m.group(1), m.group(2), m.group(3), source))
    return edges


class GraphRetriever(Retriever):
    """
    STEP2: 関係性探索（企業知識グラフ）。
    ベクトル/BM25 が苦手な「複数文書をまたぐ関係連鎖」
    (例: 顧客A → 契約B → 法令C → 売上D) を多段ホップで辿る。

    グラフ構築は決定論的（記法パース）。LLMによる自動トリプル抽出は
    将来 add() の前段に抽出器を挟むだけで追加できる。
    """

    def __init__(self, storage_path: str, max_hops: int = 2):
        self._path = Path(storage_path) / "graph.json"
        self._max_hops = max_hops
        self._edges: set[Edge] = set()
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._edges = {Edge(**e) for e in raw}
        self._rebuild_adjacency()

    def _rebuild_adjacency(self) -> None:
        # 関係性探索は双方向に辿る (売上→顧客の逆引きも価値があるため)
        self._adj: dict[str, list[tuple[Edge, bool]]] = defaultdict(list)
        for e in self._edges:
            self._adj[e.subject].append((e, True))
            self._adj[e.object].append((e, False))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([e.__dict__ for e in self._edges], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, chunks: list[RetrievedChunk]) -> None:
        added = False
        for c in chunks:
            for e in parse_triples(c.text, c.source):
                if e not in self._edges:
                    self._edges.add(e)
                    added = True
        if added:
            self._save()
            self._rebuild_adjacency()

    def _seed_nodes(self, query: str) -> dict[str, int]:
        """クエリとのトークン重なりでエントリポイントとなるノードを探す。"""
        q_tokens = {t for t in tokenize(query) if len(t) >= 2}
        seeds: dict[str, int] = {}
        for node in self._adj:
            overlap = len(q_tokens & {t for t in tokenize(node) if len(t) >= 2})
            if overlap > 0:
                seeds[node] = overlap
        return seeds

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        seeds = self._seed_nodes(query)
        results: list[RetrievedChunk] = []
        seen_paths: set[str] = set()

        for seed, strength in sorted(seeds.items(), key=lambda kv: kv[1], reverse=True):
            for path_text, sources, hops in self._walk(seed):
                if path_text in seen_paths:
                    continue
                seen_paths.add(path_text)
                results.append(RetrievedChunk(
                    text=path_text,
                    source=",".join(sorted(sources)),
                    # シード一致が強く、ホップが浅いほど高スコア
                    score=strength / hops,
                ))

        # 他のパスの接頭辞にすぎないパスは除外する（極大パスのみ返す）。
        # 1ホップの事実は通常チャンク側でも拾えるが、深い連鎖はグラフ固有の価値。
        texts = [c.text for c in results]
        results = [
            c for c in results
            if not any(t != c.text and t.startswith(c.text) for t in texts)
        ]

        results.sort(key=lambda c: c.score, reverse=True)
        return results[:top_k]

    def _walk(self, seed: str):
        """seed から max_hops 以内の関係パスを列挙する (DFS)。"""

        def dfs(node: str, path_text: str, sources: set[str], visited: set[str], depth: int):
            if depth >= self._max_hops:
                return
            for edge, forward in self._adj.get(node, []):
                nxt = edge.object if forward else edge.subject
                if nxt in visited:
                    continue
                hop = (
                    f" -[{edge.relation}]-> {nxt}" if forward
                    else f" <-[{edge.relation}]- {nxt}"
                )
                new_text = path_text + hop
                new_sources = sources | {edge.source}
                yield new_text, new_sources, depth + 1
                yield from dfs(nxt, new_text, new_sources, visited | {nxt}, depth + 1)

        yield from dfs(seed, seed, set(), {seed}, 0)

    def count(self) -> int:
        return len(self._edges)
