import pytest

from titans.retrieval.base import RetrievedChunk, tokenize
from titans.retrieval.bm25_store import BM25Retriever
from titans.retrieval.embedder import HashingEmbedder
from titans.retrieval.ingest import chunk_text, load_directory
from titans.retrieval.knowledge_base import KnowledgeBase
from titans.retrieval.merger import reciprocal_rank_fusion
from titans.retrieval.qdrant_store import QdrantRetriever


# --- tokenizer ---

def test_tokenize_japanese_bigrams():
    tokens = tokenize("医療診断")
    assert "医療" in tokens
    assert "療診" in tokens
    assert "医" in tokens


def test_tokenize_mixed():
    tokens = tokenize("ROI計算とPMDA承認")
    assert "roi" in tokens
    assert "pmda" in tokens
    assert "計算" in tokens


# --- embedder ---

def test_hashing_embedder_deterministic_and_normalized():
    e = HashingEmbedder(dim=64)
    v1 = e.embed("キャッシュフロー分析")
    v2 = e.embed("キャッシュフロー分析")
    assert v1 == v2
    assert len(v1) == 64
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-6


def test_hashing_embedder_similarity_orders_correctly():
    e = HashingEmbedder(dim=512)
    q = e.embed("医療機器の承認")
    near = e.embed("医療機器プログラムの承認には時間がかかる")
    far = e.embed("株価が上昇して投資家が喜んだ")
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert dot(q, near) > dot(q, far)


# --- chunking / ingest ---

def test_chunk_text_respects_max_chars():
    text = "\n\n".join(f"段落{i}です。" * 10 for i in range(10))
    chunks = chunk_text(text, max_chars=200)
    assert all(len(c) <= 200 for c in chunks)
    assert len(chunks) > 1


def test_load_directory(tmp_path):
    (tmp_path / "a.md").write_text("テスト知識Aです。", encoding="utf-8")
    (tmp_path / "b.txt").write_text("テスト知識Bです。", encoding="utf-8")
    (tmp_path / "c.pdf").write_text("無視されるべき", encoding="utf-8")
    chunks = load_directory(str(tmp_path))
    sources = {c.source for c in chunks}
    assert sources == {"a.md", "b.txt"}


# --- BM25 ---

def test_bm25_finds_exact_keyword(tmp_path):
    r = BM25Retriever(str(tmp_path))
    r.add([
        RetrievedChunk(text="薬機法に基づくPMDA承認が必要です", source="legal"),
        RetrievedChunk(text="ROIは3年で15%を基準とする", source="finance"),
        RetrievedChunk(text="今日の天気は晴れです", source="misc"),
    ])
    results = r.search("PMDA承認の要否", top_k=2)
    assert results[0].source == "legal"


def test_bm25_persistence_roundtrip(tmp_path):
    # 注: BM25のIDFは「全文書の半数以下に出現」して初めて正になるため
    # (N=2,df=1 では log(1.5/1.5)=0)、3文書以上で永続化の往復を検証する
    r1 = BM25Retriever(str(tmp_path))
    r1.add([
        RetrievedChunk(text="段階投資を原則とする", source="policy"),
        RetrievedChunk(text="天気は晴れである", source="misc"),
        RetrievedChunk(text="会議は月曜に開催する", source="ops"),
    ])
    r2 = BM25Retriever(str(tmp_path))
    assert r2.count() == 3
    assert r2.search("段階投資", top_k=1)[0].source == "policy"


# --- Qdrant local mode ---

def test_qdrant_add_and_search(tmp_path):
    r = QdrantRetriever(str(tmp_path / "q"), HashingEmbedder(dim=128))
    r.add([
        RetrievedChunk(text="キャッシュフローが12ヶ月で枯渇するリスク", source="finance"),
        RetrievedChunk(text="個人情報保護法の要配慮個人情報", source="legal"),
    ])
    assert r.count() == 2
    results = r.search("キャッシュフローのリスク", top_k=1)
    assert results[0].source == "finance"
    r.close()


# --- merger ---

def test_rrf_merges_and_dedupes():
    a = [RetrievedChunk(text="X", source="s1"), RetrievedChunk(text="Y", source="s2")]
    b = [RetrievedChunk(text="Y", source="s2"), RetrievedChunk(text="Z", source="s3")]
    merged = reciprocal_rank_fusion([a, b], top_k=3)
    texts = [c.text for c in merged]
    assert texts[0] == "Y"          # 両方に出現 → 最上位
    assert len(texts) == len(set(texts)) == 3


# --- KnowledgeBase facade ---

def test_knowledge_base_end_to_end(tmp_path):
    kdir = tmp_path / "knowledge"
    kdir.mkdir()
    (kdir / "policy.md").write_text(
        "新規事業の投資上限は第1フェーズで2億円とする。", encoding="utf-8"
    )
    (kdir / "legal.md").write_text(
        "診断支援ソフトウェアは薬機法のSaMDに該当しうる。", encoding="utf-8"
    )
    kb = KnowledgeBase(storage_dir=str(tmp_path / "storage"))
    n = kb.ingest_directory(str(kdir))
    assert n == 2
    text = kb.retrieve_as_text("投資上限はいくらか", top_k=2)
    assert "2億円" in text
    assert "出典" in text
    kb.close()


# --- flow integration: tasks receive retrieved knowledge ---

def test_tasks_include_retrieved_knowledge():
    from titans.agents.board_agents import create_board_agents
    from titans.brain.stub_provider import StubProvider
    from titans.tasks.board_tasks import create_board_tasks
    from titans.utils.config_loader import AppConfig

    agents = create_board_agents(StubProvider().get_llm(), AppConfig())
    tasks = create_board_tasks(
        agents, "テスト課題", retrieved_knowledge="[出典: policy.md]\n投資上限は2億円"
    )
    for t in tasks:
        assert "【関連知識】" in t.description
        assert "2億円" in t.description
