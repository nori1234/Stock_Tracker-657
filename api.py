#!/usr/bin/env python3
"""
Titans Board v2.0 — REST API

起動:
  python api.py                              # Ollama (config.yaml の設定)
  python api.py --anthropic                  # Anthropic API (ANTHROPIC_API_KEY 必須)
  python api.py --anthropic --model claude-sonnet-4-6

呼び出し例:
  curl -X POST http://localhost:8000/meeting \
       -H "Content-Type: application/json" \
       -d '{"agenda": "新規事業としてAI医療診断支援サービスを展開したい"}'
"""

import os
import sys

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import asyncio
from contextlib import asynccontextmanager
from functools import partial
from typing import Optional

import uvicorn
import click
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from titans.utils.config_loader import load_config, create_brain_provider
from titans.memory import create_memory_store, MemoryEntry, CATEGORIES


# ── グローバル状態（起動時に1回だけ初期化） ─────────────────────────────────

_app_config = None
_brain_provider = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _app_config, _brain_provider
    _app_config = load_config()
    # 起動フラグからの上書き（env var 経由）
    if os.environ.get("TITANS_PROVIDER"):
        _app_config.brain.provider = os.environ["TITANS_PROVIDER"]
    if os.environ.get("TITANS_MODEL"):
        _app_config.brain.model = os.environ["TITANS_MODEL"]
    _brain_provider = create_brain_provider(_app_config)
    print(f"[Titans] provider={_app_config.brain.provider}  model={_app_config.brain.model}")
    yield


app = FastAPI(
    title="Titans Board v2.0",
    description=(
        "AI 取締役会 API。POST /meeting に議題を投げると "
        "CFO→CLO→CEO草稿→監査役→CEO最終 の5役員が審議して結果を返す。"
    ),
    version="2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── リクエスト / レスポンス モデル ──────────────────────────────────────────

class MeetingRequest(BaseModel):
    agenda: str
    no_rag: bool = False
    no_memory: bool = False

    model_config = {"json_schema_extra": {
        "example": {
            "agenda": "新規事業として、AIを活用した医療診断支援サービスを日本市場で展開したい。初期投資5億円、3年でのROI達成が目標。",
            "no_rag": False,
            "no_memory": False,
        }
    }}


class MeetingResponse(BaseModel):
    agenda: str
    cfo: str
    clo: str
    ceo_draft: str
    auditor: str
    ceo_final: str
    retrieved_knowledge: str = ""
    long_term_memory: str = ""
    saved_to: Optional[str] = None


class MemoryRequest(BaseModel):
    content: str
    category: str = "経営方針"

    model_config = {"json_schema_extra": {
        "example": {"content": "ギャンブル関連事業への参入禁止", "category": "禁止事項"}
    }}


class IngestRequest(BaseModel):
    directory: str = "./knowledge"


# ── ヘルパー ─────────────────────────────────────────────────────────────────

def _make_knowledge_base(cfg):
    from titans.retrieval.knowledge_base import KnowledgeBase
    return KnowledgeBase(
        storage_dir=cfg.retrieval.storage_dir,
        embedder_kind=cfg.retrieval.embedder,
        embedding_dim=cfg.retrieval.embedding_dim,
        ollama_base_url=cfg.brain.base_url,
        graph_enabled=cfg.retrieval.graph_enabled,
        graph_max_hops=cfg.retrieval.graph_max_hops,
    )


def _run_meeting_sync(agenda: str, no_rag: bool, no_memory: bool) -> MeetingResponse:
    from titans.flows.board_meeting_flow import BoardMeetingFlow
    from titans.report.renderer import ReportRenderer

    cfg = _app_config

    kb = None
    if cfg.retrieval.enabled and not no_rag:
        kb = _make_knowledge_base(cfg)

    ms = None
    if cfg.memory.enabled and not no_memory:
        ms = create_memory_store(cfg)

    flow = BoardMeetingFlow(
        brain_provider=_brain_provider,
        config=cfg,
        knowledge_base=kb,
        memory_store=ms,
    )
    flow.kickoff(inputs={"user_input": agenda})
    if kb:
        kb.close()

    report = flow.state.meeting_report
    if report is None:
        raise ValueError("レポートの生成に失敗しました")

    saved = None
    if cfg.output.save_to_file:
        saved = str(ReportRenderer().save_to_file(report, cfg.output.output_dir))

    return MeetingResponse(
        agenda=agenda,
        cfo=report.cfo_output,
        clo=report.clo_output,
        ceo_draft=report.ceo_draft_output,
        auditor=report.auditor_output,
        ceo_final=report.ceo_final_output,
        retrieved_knowledge=report.retrieved_knowledge,
        long_term_memory=report.long_term_memory,
        saved_to=saved,
    )


# ── エンドポイント ────────────────────────────────────────────────────────────

@app.get("/health", summary="接続確認")
def health():
    ok = _brain_provider.health_check()
    return {
        "status": "ok" if ok else "fail",
        "provider": _app_config.brain.provider,
        "model": _app_config.brain.model,
    }


@app.post("/meeting", response_model=MeetingResponse, summary="取締役会を開催する")
async def run_meeting(req: MeetingRequest):
    """
    議題を渡すと CFO→CLO→CEO草稿→監査役→CEO最終 の順で審議し、全出力を返す。

    - Haiku: 約 1〜2 分
    - Sonnet: 約 2〜4 分
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(_run_meeting_sync, req.agenda, req.no_rag, req.no_memory),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories", summary="長期記憶を一覧表示")
def list_memories():
    ms = create_memory_store(_app_config)
    return [
        {"category": e.category, "content": e.content, "timestamp": e.timestamp}
        for e in ms.entries()
    ]


@app.post("/memories", status_code=201, summary="長期記憶に追加")
def add_memory(req: MemoryRequest):
    if req.category not in CATEGORIES:
        raise HTTPException(400, detail=f"カテゴリは {list(CATEGORIES)} のいずれかにしてください")
    ms = create_memory_store(_app_config)
    ms.remember(MemoryEntry(category=req.category, content=req.content))
    return {"added": True, "total": ms.count()}


@app.post("/ingest", summary="知識ディレクトリを取り込む")
def ingest_knowledge(req: IngestRequest):
    kb = _make_knowledge_base(_app_config)
    n = kb.ingest_directory(req.directory)
    counts = kb.count()
    kb.close()
    return {"chunks_ingested": n, **counts}


# ── エントリポイント ─────────────────────────────────────────────────────────

@click.command()
@click.option("--host", default="127.0.0.1", help="ホスト (外部公開する場合は 0.0.0.0)")
@click.option("--port", default=8000, help="ポート番号")
@click.option("--anthropic", "use_anthropic", is_flag=True,
              help="Anthropic API を使う (ANTHROPIC_API_KEY 必須)")
@click.option("--model", "model_override", default=None,
              help="モデル上書き (例: claude-sonnet-4-6)")
def serve(host, port, use_anthropic, model_override):
    """Titans Board v2.0 API サーバーを起動する"""
    if use_anthropic:
        os.environ["TITANS_PROVIDER"] = "anthropic"
        os.environ.setdefault("TITANS_MODEL", "claude-haiku-4-5-20251001")
    if model_override:
        os.environ["TITANS_MODEL"] = model_override

    print(f"\n  Titans Board API")
    print(f"  http://{host}:{port}/docs  ← ブラウザで開くと対話式ドキュメント")
    print(f"  http://{host}:{port}/health\n")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    serve()
