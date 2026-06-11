from titans.retrieval.base import RetrievedChunk
from titans.retrieval.graph_store import GraphRetriever, parse_triples
from titans.retrieval.knowledge_base import KnowledgeBase


SAMPLE = """これは普通の文章で無視される。
顧客A -[契約]-> 契約B
契約B -[準拠]-> 法令C
契約B -[計上先]-> 売上D
"""


def test_parse_triples_ignores_prose():
    edges = parse_triples(SAMPLE, source="rel.md")
    assert len(edges) == 3
    assert edges[0].subject == "顧客A"
    assert edges[0].relation == "契約"
    assert edges[0].object == "契約B"


def test_multi_hop_traversal_finds_indirect_relation(tmp_path):
    """設計書の例: 顧客A → 契約B → 法令C。
    「顧客A」と「法令C」は同一文書に共起しないが、2ホップ探索で繋がる。"""
    g = GraphRetriever(str(tmp_path), max_hops=2)
    g.add([RetrievedChunk(text=SAMPLE, source="rel.md")])
    results = g.search("顧客Aのリスクを確認したい", top_k=5)
    joined = " / ".join(c.text for c in results)
    assert "法令C" in joined          # 2ホップ先に到達
    assert "売上D" in joined
    assert results[0].text.startswith("顧客A")


def test_reverse_traversal(tmp_path):
    """売上側から顧客を逆引きできる（双方向探索）。"""
    g = GraphRetriever(str(tmp_path), max_hops=2)
    g.add([RetrievedChunk(text=SAMPLE, source="rel.md")])
    results = g.search("売上Dの内訳", top_k=5)
    joined = " / ".join(c.text for c in results)
    assert "契約B" in joined


def test_persistence_and_dedup(tmp_path):
    g1 = GraphRetriever(str(tmp_path))
    chunk = RetrievedChunk(text=SAMPLE, source="rel.md")
    g1.add([chunk])
    g1.add([chunk])           # 再取り込みしても重複しない
    assert g1.count() == 3
    g2 = GraphRetriever(str(tmp_path))
    assert g2.count() == 3


def test_no_seed_returns_empty(tmp_path):
    g = GraphRetriever(str(tmp_path))
    g.add([RetrievedChunk(text=SAMPLE, source="rel.md")])
    assert g.search("全く無関係な宇宙旅行", top_k=5) == []


def test_max_hops_limits_depth(tmp_path):
    g = GraphRetriever(str(tmp_path), max_hops=1)
    g.add([RetrievedChunk(text=SAMPLE, source="rel.md")])
    joined = " / ".join(c.text for c in g.search("顧客A", top_k=10))
    assert "契約B" in joined
    assert "法令C" not in joined      # 2ホップ先には届かない


def test_knowledge_base_three_way_fusion(tmp_path):
    """Qdrant + BM25 + Graph の3系統がRRFで統合される。"""
    kdir = tmp_path / "k"
    kdir.mkdir()
    (kdir / "rel.md").write_text(
        "顧客メディカル社 -[締結]-> 利用契約\n利用契約 -[準拠]-> 薬機法\n",
        encoding="utf-8",
    )
    (kdir / "doc.md").write_text(
        "顧客メディカル社は大手医療法人グループである。", encoding="utf-8"
    )
    kb = KnowledgeBase(storage_dir=str(tmp_path / "s"))
    kb.ingest_directory(str(kdir))
    counts = kb.count()
    assert counts["graph"] == 2
    text = kb.retrieve_as_text("顧客メディカル社との取引リスク", top_k=4)
    assert "薬機法" in text           # グラフ経由の2ホップ関係
    assert "医療法人" in text         # 通常チャンク経由
    kb.close()
