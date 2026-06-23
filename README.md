# Titans Board v2.0

AI executive board system. Four agents (CFO / CLO / CEO / Auditor) share a single LLM instance ("One Brain"), deliberate on a management agenda using RAG retrieval and long-term memory, and produce a final board report.

---

## 株価 LINE 通知 (stocks/)

このリポジトリは「株価を取得し、条件を満たしたら LINE に通知する」ツールへ段階的に移行中です。AI 取締役会 (`titans/`) はまだ残っていますが、株価通知機能は `stocks/` パッケージとして独立しています。

> **注意:** LINE Notify は 2025-03-31 に終了したため、通知は **LINE Messaging API の push** を使います。LINE Developers でチャネルを作成し、長期のチャネルアクセストークンと送信先 (userId/groupId) を用意してください。

### セットアップ

```bash
pip install -r requirements.txt          # yfinance / requests を含む

cp .env.example .env                      # 以下を設定
#   LINE_CHANNEL_ACCESS_TOKEN=...
#   LINE_TO=...                           # 送信先 userId / groupId
```

`stocks.yaml` で監視銘柄とアラート条件を定義します（日本株は `7203.T`、米国株は `AAPL` 形式）。

```yaml
watchlist:
  - symbol: "7203.T"
    name: "トヨタ自動車"
    conditions:
      - type: price_below       # 現在値 <= value
        value: 2500
      - type: change_pct_below  # 前日比(%) <= value
        value: -3
  - symbol: "AAPL"
    conditions:
      - type: change_pct_above  # 前日比(%) >= value
        value: 5
```

条件タイプ: `price_above` / `price_below` / `change_pct_above` / `change_pct_below`

### 実行

```bash
python stock_notify.py            # 条件成立した銘柄だけ LINE に通知
python stock_notify.py --dry-run  # 送信せず、取得値と通知本文を確認
```

#### AI 取締役会に議論させる (`--discuss`)

発火した銘柄を `titans/` の取締役会 (CFO→CLO→CEO草稿→監査役→CEO最終) にかけ、投資判断の結論を LINE 本文に添えます。実 LLM (Ollama か Anthropic) が必要です。

```bash
# Ollama (config.yaml の brain 設定を使用)
python stock_notify.py --discuss --dry-run

# Anthropic API (ANTHROPIC_API_KEY 必須)
python stock_notify.py --discuss --anthropic --model claude-haiku-4-5-20251001
```

通知本文には各銘柄の現在値・発火条件に加えて「🤖 取締役会の見解」が付きます。取締役会が失敗してもアラート自体は通常どおり通知されます (見解だけ欠落)。

#### 重複通知の抑制 (エッジトリガー)

定期実行では、条件が成立し続けている間に毎回通知されると煩わしいため、**いったん成立した条件は再武装まで再通知しません**。アクティブな条件キーを状態ファイル (既定: `./storage/stock_alert_state.json`) に保存し、

- 条件が成立し続ける間 … 抑制（再送しない）
- 条件がいったん外れる … 再武装
- 再び成立する … 改めて通知

として扱います（既定で有効）。

```bash
python stock_notify.py --no-dedup                       # 抑制を無効化 (毎回通知)
python stock_notify.py --state-file /path/state.json    # 状態ファイルの場所を変更
```

`--dry-run` では状態ファイルを更新しないため、安全に本文だけ確認できます。

#### 定期実行

**サーバーがある場合 (cron 例 — 平日 9〜15 時に 15 分おき):**

```
*/15 9-15 * * 1-5  cd /path/to/repo && python stock_notify.py >> stock.log 2>&1
```

**サーバー無しで自動運用 (GitHub Actions):**

`.github/workflows/stock-notify.yml` を同梱しています。平日の日本市場 (JST 9:00-15:30) と米国市場 (ET 9:30-17:00) の時間帯に 30 分おきで実行し、条件成立時に LINE 通知します。

1. リポジトリの **Settings → Secrets and variables → Actions** に Secrets を登録:
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_TO`
2. `stocks.yaml` の `watchlist` を編集してコミット（トークンは空のまま。Secrets が環境変数で渡る）。
3. **Actions タブ → Stock LINE Notify → Run workflow** で手動実行して疎通確認（`dry_run` を ON にすれば送信せず確認のみ）。

重複抑制の状態ファイル (`storage/`) は `actions/cache` で run 間に持ち越されるため、成立し続ける条件の再通知は GitHub Actions 上でも抑制されます。依存は軽量な `requirements-stock.txt`（crewai を含まない）でインストールされます。

テスト (ネットワーク非依存):

```bash
python -m pytest tests/test_stocks.py -q
```

---

## Table of Contents

1. [Architecture](#architecture)
2. [Directory Structure](#directory-structure)
3. [Configuration Reference](#configuration-reference)
4. [CLI Reference](#cli-reference)
5. [REST API Reference](#rest-api-reference)
6. [Brain Providers](#brain-providers)
7. [Retrieval Layer](#retrieval-layer)
8. [Memory System](#memory-system)
9. [Knowledge Graph Notation](#knowledge-graph-notation)
10. [Setup & Running](#setup--running)
11. [Testing](#testing)
12. [Known Issues & Constraints](#known-issues--constraints)
13. [Phase 5: TTT-Mamba](#phase-5-ttt-mamba)

---

## Architecture

### Core Principle: One Brain

All four CrewAI agents share **the same `crewai.LLM` Python object**. Persona switching is achieved purely through each agent's `role` + `backstory` (injected as the SystemMessage by CrewAI). There is exactly one model instance in memory at runtime.

```
config.yaml
  └─ create_brain_provider()  →  OllamaProvider / AnthropicProvider / ...
       └─ provider.get_llm()  →  crewai.LLM  (singleton, cached)
            ├─ Agent(role="CFO ...",      llm=shared_llm)
            ├─ Agent(role="CLO ...",      llm=shared_llm)
            ├─ Agent(role="CEO ...",      llm=shared_llm)
            └─ Agent(role="Auditor ...", llm=shared_llm)
```

### Execution Flow (CrewAI Flow)

```
User Input
   │
   ▼
prepare_context (@start)
   ├─ MemoryStore.load_context()      → long_term_memory  (always includes 禁止事項/経営方針)
   └─ KnowledgeBase.retrieve_as_text() → retrieved_knowledge (Qdrant+BM25+Graph → RRF)
   │
   ▼
kickoff_meeting (@listen)
   CFO task  (context: none)
   CLO task  (context: [CFO])
   CEO draft (context: [CFO, CLO])
   Auditor   (context: [CFO, CLO, CEO draft])
   CEO final (context: [CFO, CLO, CEO draft, Auditor])
   │
   ▼
on_meeting_complete (@listen)
   └─ Writes CEO final decision → MemoryStore as category "過去意思決定"
   │
   ▼
MeetingReport  (Rich console panels + JSON saved to ./outputs/)
```

Context chains are **explicit** (`Task.context=[...]`). CrewAI's auto-chaining only passes the immediately prior task; explicit chains are required so the Auditor sees all three prior outputs.

---

## Directory Structure

```
titans-board/
├── main.py                    # CLI entry point (click). All flags documented in CLI Reference.
├── api.py                     # FastAPI REST server. All endpoints documented in API Reference.
├── config.yaml                # Runtime configuration. All keys documented in Config Reference.
├── requirements.txt           # Pinned deps. crewai==1.14.6 MUST stay pinned (see Constraints).
├── .env.example               # Environment variable template.
├── colab_quickstart.ipynb     # Google Colab notebook. Path A = Anthropic API, Path B = Ollama.
├── knowledge/                 # Sample knowledge files for --ingest.
│   ├── company_policy.md
│   ├── legal_notes.md
│   └── relations.md           # Contains graph triples: A -[rel]-> B notation.
├── titans/
│   ├── brain/
│   │   ├── base.py            # BrainProvider ABC: get_llm() → LLM, health_check(), model_info()
│   │   ├── ollama_provider.py # OllamaProvider. Uses extra_body={"options":{"num_ctx":N}} (NOT extra_params).
│   │   ├── anthropic_provider.py  # AnthropicProvider. model="anthropic/<model>".
│   │   ├── openai_compatible_provider.py  # Phase 5. model="hosted_vllm/<model>" prefix required.
│   │   └── stub_provider.py   # No-op for tests. health_check() always False.
│   ├── personas/
│   │   ├── cfo.yaml           # role / goal / backstory / output_format
│   │   ├── clo.yaml
│   │   ├── ceo.yaml
│   │   └── auditor.yaml
│   ├── agents/
│   │   └── board_agents.py    # create_board_agents(shared_llm, config) → dict[str, Agent]
│   ├── tasks/
│   │   └── board_tasks.py     # create_board_tasks(...) → list[Task] with explicit context chains.
│   │                          # Injects model_directive ("/no_think" for qwen3) per task.
│   ├── flows/
│   │   └── board_meeting_flow.py  # BoardMeetingFlow(Flow[MeetingState]). 3 @start/@listen steps.
│   ├── retrieval/
│   │   ├── base.py            # RetrievedChunk, Retriever ABC, tokenize() (CJK + ASCII, zero deps)
│   │   ├── embedder.py        # HashingEmbedder (offline, dim=512), OllamaEmbedder (auto-detects dim)
│   │   ├── qdrant_store.py    # QdrantRetriever. Local in-process mode (no server). Auto-recreates
│   │   │                      # collection on embedder dimension mismatch.
│   │   ├── bm25_store.py      # BM25Retriever. JSON persistence. Uses tokenize().
│   │   ├── graph_store.py     # GraphRetriever. Parses "A -[rel]-> B" triples. DFS bidirectional
│   │   │                      # multi-hop. Returns maximal paths only.
│   │   ├── merger.py          # reciprocal_rank_fusion(result_lists, top_k, k=60)
│   │   ├── ingest.py          # load_directory(): reads .txt/.md, chunks by paragraph
│   │   └── knowledge_base.py  # KnowledgeBase facade: ingest_directory(), retrieve_as_text(), count()
│   ├── memory/
│   │   ├── base.py            # MemoryEntry, MemoryStore ABC, CATEGORIES, ALWAYS_INCLUDE
│   │   ├── local_store.py     # LocalMemoryStore: JSON at storage_dir/memory.json. load_context()
│   │   │                      # always includes 禁止事項+経営方針; ranks others by token overlap.
│   │   ├── letta_store.py     # LettaMemoryStore: agents.passages.create/list (lazy import).
│   │   └── __init__.py        # create_memory_store(config), exports CATEGORIES, MemoryEntry
│   ├── report/
│   │   └── renderer.py        # MeetingReport dataclass + ReportRenderer (Rich panels + JSON save)
│   └── utils/
│       ├── config_loader.py   # AppConfig (pydantic), load_config(), create_brain_provider()
│       └── context_builder.py # ContextComponents dataclass + build_task_description()
│                              # assembles [LTM] + [Knowledge] + [Input] + [Task]
├── tests/
│   ├── conftest.py            # Sets CREWAI_DISABLE_TELEMETRY=true, OTEL_SDK_DISABLED=true
│   ├── test_brain.py          # BrainProvider tests incl. Phase 5 OpenAI-compatible
│   ├── test_agents.py         # One-brain singleton assertion
│   ├── test_flow.py           # E2E flow with mocked LLM
│   ├── test_graph.py          # GraphRetriever: parse, search, multi-hop
│   ├── test_memory.py         # MemoryStore: remember, load_context, write-back
│   └── test_retrieval.py      # Qdrant, BM25, merger, embedder
└── outputs/                   # Auto-created. meeting_YYYYMMDD_HHMMSS.json saved here.
```

---

## Configuration Reference

File: `config.yaml`

### `brain` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `provider` | str | `"ollama"` | `"ollama"` \| `"anthropic"` \| `"openai_compatible"` \| `"stub"` |
| `model` | str | `"qwen3:4b"` | Ollama tag, `claude-*` for anthropic, or model name for openai_compatible |
| `base_url` | str | `"http://localhost:11434"` | Ollama / OpenAI-compatible server URL |
| `temperature` | float | `0.3` | LLM temperature |
| `num_ctx` | int | `4096` | Ollama KV cache context window (affects inference speed) |
| `max_tokens` | int | `2048` | Max output tokens per LLM call. EOS stops generation early; this is a safety cap. |
| `disable_thinking` | bool | `true` | Inject `/no_think` directive for qwen3 models to suppress chain-of-thought tokens |
| `timeout` | int | `180` | LLM call timeout in seconds |
| `api_key` | str | `""` | openai_compatible only. Falls back to env `TITANS_LLM_API_KEY`, then `"not-needed"` |

### `retrieval` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable RAG retrieval |
| `storage_dir` | str | `"./storage"` | Directory for Qdrant and BM25 persistence |
| `top_k` | int | `3` | Number of chunks to inject per meeting |
| `embedder` | str | `"hashing"` | `"hashing"` (offline, lexical) \| `"ollama"` (requires nomic-embed-text or similar) |
| `embedding_dim` | int | `512` | Vector dimension for hashing embedder. OllamaEmbedder auto-detects and ignores this. |
| `graph_enabled` | bool | `true` | Enable GraphRAG relationship traversal |
| `graph_max_hops` | int | `2` | Maximum hops in graph DFS |

### `memory` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable long-term memory injection |
| `provider` | str | `"local"` | `"local"` (JSON file) \| `"letta"` (requires letta-client + Letta server) |
| `storage_dir` | str | `"./storage"` | Directory for memory.json |
| `top_k` | int | `5` | Max memory entries to inject (禁止事項/経営方針 always injected regardless) |
| `letta_base_url` | str | `"http://localhost:8283"` | Letta server URL (letta provider only) |
| `letta_agent_id` | str | `""` | Letta agent ID (letta provider only) |

### `meeting` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `language` | str | `"ja"` | Output language hint |
| `verbose` | bool | `false` | Enable CrewAI verbose task logs |
| `max_iter` | int | `1` | Max CrewAI agent retry iterations. Keep at 1 to prevent 3x slowdown from retry loops. |

### `output` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `save_to_file` | bool | `true` | Save JSON report to output_dir |
| `output_dir` | str | `"./outputs"` | Output directory |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Required for `brain.provider: anthropic` |
| `TITANS_LLM_API_KEY` | API key for openai_compatible provider (optional for local servers) |
| `OLLAMA_BASE_URL` | Overrides `brain.base_url` for Ollama |
| `TITANS_PROVIDER` | Runtime override for `brain.provider` (used by api.py `--anthropic` flag) |
| `TITANS_MODEL` | Runtime override for `brain.model` |
| `CREWAI_DISABLE_TELEMETRY` | Set to `"true"` to prevent 30s telemetry timeout (auto-set by main.py) |
| `OTEL_SDK_DISABLED` | Set to `"true"` alongside above (auto-set by main.py) |

---

## CLI Reference

Entry point: `python main.py`

```
python main.py [OPTIONS] [USER_INPUT]
```

| Flag | Description |
|------|-------------|
| `"<agenda>"` | Run board meeting with this agenda string |
| `--anthropic` | Switch to Anthropic API without editing config.yaml. Defaults to claude-haiku-4-5-20251001. |
| `--model <id>` | Override brain.model at runtime (e.g. `--model claude-sonnet-4-6`) |
| `--health-check` | Check LLM connectivity and print model info. Exit 0 = OK, 1 = FAIL. |
| `--ingest <dir>` | Ingest all .txt/.md files in directory into RAG stores and exit |
| `--remember <text>` | Add one entry to long-term memory and exit |
| `--category <cat>` | Category for --remember. One of: `ユーザー嗜好` `経営方針` `過去意思決定` `禁止事項` `顧客情報` |
| `--memories` | List all long-term memory entries and exit |
| `--no-rag` | Disable RAG retrieval for this run |
| `--no-memory` | Disable long-term memory for this run |
| `--verbose` | Enable CrewAI verbose task execution logs |
| `--no-save` | Do not save JSON output to file |
| `--config <path>` | Path to config.yaml (default: `config.yaml`) |

---

## REST API Reference

Entry point: `python api.py`

```
python api.py [--host 127.0.0.1] [--port 8000] [--anthropic] [--model <id>]
```

Interactive docs available at `http://localhost:8000/docs` after startup.

---

### `GET /health`

Check LLM connectivity.

**Response**
```json
{
  "status": "ok",
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001"
}
```

---

### `POST /meeting`

Run a board meeting. Blocking; takes 1–4 minutes depending on model.

**Request**
```json
{
  "agenda": "string (required)",
  "no_rag": false,
  "no_memory": false
}
```

**Response**
```json
{
  "agenda": "string",
  "cfo": "CFO financial analysis (markdown)",
  "clo": "CLO legal review (markdown)",
  "ceo_draft": "CEO strategy draft (markdown)",
  "auditor": "Auditor review + revision instructions (markdown)",
  "ceo_final": "CEO final decision (markdown)",
  "retrieved_knowledge": "RAG chunks that were injected (may be empty)",
  "long_term_memory": "Memory entries that were injected (may be empty)",
  "saved_to": "./outputs/meeting_YYYYMMDD_HHMMSS.json or null"
}
```

**Example**
```bash
curl -X POST http://localhost:8000/meeting \
     -H "Content-Type: application/json" \
     -d '{"agenda": "AI医療診断支援サービスを日本市場で展開したい。初期投資5億円、3年ROI。"}' \
     --max-time 300
```

```python
import requests
r = requests.post("http://localhost:8000/meeting",
                  json={"agenda": "..."}, timeout=300)
print(r.json()["ceo_final"])
```

---

### `GET /memories`

List all long-term memory entries.

**Response**
```json
[
  {
    "category": "禁止事項",
    "content": "ギャンブル・アダルト関連事業への参入禁止",
    "timestamp": "2026-06-13T00:00:00"
  }
]
```

---

### `POST /memories`

Add a long-term memory entry.

**Request**
```json
{
  "content": "string (required)",
  "category": "経営方針"
}
```

Valid categories: `ユーザー嗜好` `経営方針` `過去意思決定` `禁止事項` `顧客情報`

**Response** (201)
```json
{ "added": true, "total": 3 }
```

---

### `POST /ingest`

Ingest a knowledge directory into RAG stores.

**Request**
```json
{ "directory": "./knowledge" }
```

**Response**
```json
{
  "chunks_ingested": 42,
  "qdrant": 42,
  "bm25": 42,
  "graph": 10
}
```

---

## Brain Providers

### `ollama`
- Uses `crewai.LLM(model="ollama/<model>", ...)`
- Ollama-specific options (`num_ctx`, `num_predict`) passed via `extra_body={"options": {...}}` — NOT as top-level kwargs (causes `unexpected keyword argument` error)
- Health check: `ollama.Client.list()`
- Requires Ollama server running at `brain.base_url`

### `anthropic`
- Uses `crewai.LLM(model="anthropic/<model>", ...)`
- Requires `ANTHROPIC_API_KEY` env var
- No local server needed
- Health check: verifies `ANTHROPIC_API_KEY` is set

### `openai_compatible` (Phase 5)
- Uses `crewai.LLM(model="hosted_vllm/<model>", base_url=..., ...)`
- The `hosted_vllm/` prefix is in CrewAI's `SUPPORTED_NATIVE_PROVIDERS` and accepts any model name without litellm. Using `openai/<model>` fails with `ImportError: LiteLLM fallback not installed`.
- The prefix is consumed by routing; `llm.model` stores the bare model name.
- API key defaults to env `TITANS_LLM_API_KEY` or `"not-needed"` (most local servers don't validate)
- Health check: HTTP GET `/v1/models` with Bearer token

### `stub`
- No-op for testing. `health_check()` always returns `False`.
- Uses `LLM(model="ollama/stub", base_url="http://localhost:99999")` — never actually called

---

## Retrieval Layer

Three retrievers merged via Reciprocal Rank Fusion (k=60).

### STEP 1: Qdrant (semantic search)
- Local in-process mode (`QdrantClient(path=...)`) — no server process required
- Collection created at init with `embedder.dim`
- **Dimension mismatch handling**: if existing collection dim ≠ embedder.dim, collection is automatically deleted and recreated (e.g. switching from `hashing`→`ollama` embedder)

### STEP 2: GraphRetriever (relationship traversal)
- Parses `主体 -[関係]-> 客体` triples from ingested files (see [Knowledge Graph Notation](#knowledge-graph-notation))
- DFS bidirectional multi-hop traversal up to `graph_max_hops`
- Returns maximal paths only (sub-paths filtered out)
- Enables chained lookups: `顧客 → 契約 → 法令 → 規制機関`

### STEP 3: BM25 (keyword search)
- `rank_bm25` library with custom `tokenize()` (CJK unigrams+bigrams + ASCII words, zero deps)
- Persisted as JSON at `storage_dir/bm25_index.json`

### Embedders

| Kind | Description | When to use |
|------|-------------|-------------|
| `hashing` | Feature hashing (offline, deterministic, dim=512) | Default. No model needed. Lexical similarity only, not semantic. |
| `ollama` | Calls Ollama embedding model. Auto-detects actual output dim. | When `nomic-embed-text` or similar is available. Provides true semantic search. |

**OllamaEmbedder**: calls the model once at `__init__` to detect the true embedding dimension. This overrides `embedding_dim` from config, preventing shape mismatch errors (e.g. nomic-embed-text outputs 768 but config default is 512).

---

## Memory System

### Categories

```python
CATEGORIES = ("ユーザー嗜好", "経営方針", "過去意思決定", "禁止事項", "顧客情報")
ALWAYS_INCLUDE = ("禁止事項", "経営方針")
```

`ALWAYS_INCLUDE` categories are injected into every meeting regardless of `top_k` or relevance score.

### `local` provider
- Persists to `storage_dir/memory.json`
- `load_context(query, top_k)`: always includes ALWAYS_INCLUDE entries, then ranks remaining by 2-char token overlap with query, returns top_k total

### `letta` provider
- Uses `letta_client.agents.passages.create/list`
- Requires `pip install letta-client` and a running Letta server
- Configure `memory.letta_base_url` and `memory.letta_agent_id`

### Write-back
After each meeting, `on_meeting_complete()` saves the CEO final decision to memory as `category="過去意思決定"`. This enables cross-meeting continuity.

---

## Knowledge Graph Notation

Mixed into regular text files (.txt or .md). One triple per line. Only triple lines are parsed into the graph; prose is indexed by Qdrant and BM25.

```
顧客メディカル社 -[締結]-> 診断支援SaaS利用契約
診断支援SaaS利用契約 -[準拠]-> 薬機法
薬機法 -[所管]-> PMDA
```

Pattern: `<subject> -[<relation>]-> <object>`

Multi-hop example: querying "顧客メディカル社" traverses → 診断支援SaaS利用契約 → 薬機法 → PMDA, returning the full chain that vector search cannot reach.

---

## Setup & Running

### Requirements

- Python 3.11+
- For Ollama provider: Ollama server + `ollama pull qwen3:4b`
- For Anthropic provider: `ANTHROPIC_API_KEY`

### Local (recommended)

```bash
git clone https://github.com/nori1234/Stock_Tracker-657.git
cd Stock_Tracker-657

python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Anthropic (no Ollama needed)
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
python main.py --anthropic --health-check
python main.py --anthropic "経営課題をここに入力"

# OR: Ollama
ollama serve   # in a separate terminal
ollama pull qwen3:4b
python main.py --health-check
python main.py "経営課題をここに入力"

# API server
python api.py --anthropic
# → http://localhost:8000/docs
```

### Google Colab

Open the quickstart notebook (includes Path A: Anthropic API and Path B: Ollama):

`https://colab.research.google.com/github/nori1234/Stock_Tracker-657/blob/main/colab_quickstart.ipynb`

**Path A (Anthropic) is recommended** — no model download, no GPU needed, session resets don't matter.

### Optional: nomic-embed-text (semantic search upgrade)

```bash
ollama pull nomic-embed-text
# Then in config.yaml:
#   retrieval.embedder: ollama
# OllamaEmbedder auto-detects the 768-dim output; no other changes needed.
```

### Optional: Letta long-term memory

```bash
pip install letta-client
# Start Letta server, then in config.yaml:
#   memory.provider: letta
#   memory.letta_base_url: http://localhost:8283
#   memory.letta_agent_id: <your-agent-id>
```

---

## Testing

```bash
python -m pytest tests/ -q
# 44 tests, all offline (stub LLM + hashing embedder). No model download required.
```

Tests cover: brain providers, agent singleton (One Brain), flow E2E with mocked LLM, graph retrieval, memory store, BM25/Qdrant retrieval.

---

## Known Issues & Constraints

### crewai must be pinned to ==1.14.6

`requirements.txt` pins `crewai==1.14.6`. Do not upgrade without full regression testing. Newer versions (observed on Colab) have a different internal module path (`crewai/flow/runtime.py` vs `crewai/flow/flow.py`) and produce `Invalid response from LLM call - None or empty` errors.

### qwen3 thinking tokens

qwen3 models emit `<think>...</think>` reasoning tokens by default before their answer. If `max_tokens` truncates output mid-think, the answer portion is empty, causing CrewAI to raise `ValueError: Invalid response from LLM call - None or empty`.

Fix (already applied): `board_tasks.py` appends `/no_think` to every task description when `brain.model` contains `"qwen3"` and `brain.disable_thinking: true`. This is a qwen3 chat-template soft switch, not an API parameter.

### OllamaProvider num_ctx must use extra_body

crewai 1.14.6 routes `ollama/*` through an OpenAI-compatible client. Passing `num_ctx` as a top-level LLM kwarg raises `unexpected keyword argument 'num_ctx'`. It must be passed as:
```python
LLM(..., extra_body={"options": {"num_ctx": N, "num_predict": M}})
```

### openai_compatible requires hosted_vllm/ prefix

Using `openai/<model>` fails with `ImportError: LiteLLM fallback not installed`. Use `hosted_vllm/<model>` which is in `SUPPORTED_NATIVE_PROVIDERS` and accepts any model name. The prefix is consumed by routing; `llm.model` stores the bare name.

### Telemetry timeout

CrewAI's telemetry client blocks for ~30s on network-restricted environments. `main.py` sets `CREWAI_DISABLE_TELEMETRY=true` and `OTEL_SDK_DISABLED=true` at module top. `tests/conftest.py` does the same for the test suite.

### Qdrant dimension mismatch on embedder switch

Switching from `hashing` (512-dim) to `ollama` (768-dim for nomic-embed-text) without clearing storage causes `ValueError: shapes (0,512) and (768,) not aligned`. Fixed: `QdrantRetriever.__init__` checks the existing collection's dimension against `embedder.dim` and recreates the collection if they differ.

---

## Phase 5: TTT-Mamba

The `openai_compatible` brain provider is the intended connection layer for TTT-Mamba or any future SSM model. **No application code changes are needed** — only `config.yaml` needs updating.

### Route A: GGUF via Ollama

```bash
cat > Modelfile <<'EOF'
FROM ./ttt-mamba-3b.gguf
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
EOF
ollama create ttt-mamba -f Modelfile
# config.yaml: provider: ollama, model: ttt-mamba
```

### Route B: vLLM / llama.cpp server

```bash
vllm serve <model-path> --port 8000
# or: ./llama-server -m ttt-mamba.gguf --port 8000
```

```yaml
brain:
  provider: openai_compatible
  model: ttt-mamba-3b
  base_url: http://localhost:8000/v1
```

**Current status**: TTT-Mamba has no stable distribution format (no `ollama pull`, no standard GGUF release). The connection layer is implemented and tested. Model weights and quantization are the user's responsibility.

---

## Development Phases

- [x] Phase 1 — Board meeting (Ollama + Qwen3-4B + CrewAI)
- [x] Phase 2 — RAG (Qdrant + BM25 + RRF)
- [x] Phase 3 — Long-term memory (LocalJSON + Letta adapter + write-back)
- [x] Phase 4 — Knowledge graph (GraphRAG relationship traversal)
- [x] Phase 5 — OpenAI-compatible connection layer for SSM/TTT-Mamba (model weights pending)

---

## License

MIT
