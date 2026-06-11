# Titans Board v2.0

AIエグゼクティブ取締役会（CFO / CLO / CEO / 監査役）が、検索拡張と長期記憶を使って経営課題を多角的に審議し、最終レポートを出力するシステム。

## 設計思想

1. **脳は1つだけ** — 全エージェントが単一のLLMインスタンスを共有する
2. **人格は複数** — システムプロンプト（role + backstory）で人格を切り替える
3. **記憶と知識は分離** — 長期記憶（Letta/ローカル）と検索知識（Qdrant/BM25/Graph）を分ける
4. **モデルは交換可能** — `BrainProvider` 抽象でOllama/Anthropic/将来のSSMを差し替える
5. **Retrieval First** — 会議の前に関連知識と長期記憶を取得してコンテキストを構築する

## アーキテクチャ

```
User Input
   │
   ▼
prepare_context  ── Memory Loader（長期記憶）+ Retrieval Merger（RAG）
   │
   ▼
取締役会（CrewAI Flow / Sequential）
   CFO ─→ CLO ─→ CEO草稿 ─→ 監査役 ─→ CEO最終
   （全員が同一の共有LLMを使い、人格のみ切替）
   │
   ▼
on_meeting_complete  ── CEO最終判断を「過去意思決定」として長期記憶へ書き戻し
   │
   ▼
Final Report（Rich表示 + JSON保存）
```

### Retrieval Layer（`knowledge = merge(qdrant, graph, bm25)`）

| STEP | 実装 | 用途 |
|------|------|------|
| STEP1 意味検索 | Qdrant（ローカルモード、サーバー不要） | 類似案件・意味的に近い知識 |
| STEP2 関係性探索 | GraphRetriever（多段ホップ） | 顧客→契約→法令→売上 の関係連鎖 |
| STEP3 キーワード | BM25 | 法律条文・会計科目・契約番号の厳密一致 |

3系統の結果は Reciprocal Rank Fusion で統合される。

## ディレクトリ構成

```
titans/
├── brain/       # BrainProvider 抽象 + Ollama / Anthropic / Stub 実装
├── personas/    # 各エージェントの人格定義（YAML）
├── agents/      # 共有LLMを使うCrewAIエージェント生成
├── tasks/       # 5タスクの会議パイプライン（context連鎖）
├── flows/       # BoardMeetingFlow（CrewAI Flow オーケストレーション）
├── retrieval/   # Qdrant / BM25 / GraphRAG / RRF統合 / 埋め込み / 取り込み
├── memory/      # MemoryStore 抽象 + ローカルJSON / Letta 実装
├── report/      # Rich レポート描画 + JSON保存
└── utils/       # 設定ロード + Context Builder
knowledge/       # サンプル知識（.md/.txt と関係グラフ記法）
tests/           # 40+ のユニット / E2E テスト
```

## ローカル環境構築（Phase 1〜4）

検証環境: Python 3.11 / Linux・macOS。GPUは無くてもCPUで動く（Qwen3-4Bは応答が遅くなる程度）。

### 1. リポジトリと Python 仮想環境

```bash
git clone <this-repo>
cd Stock_Tracker-657

python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Ollama 本体のインストールと起動

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
# macOS: https://ollama.com/download から Ollama.app を入れる（brew install ollama も可）

# サーバーを起動（別ターミナルで起動したままにする。macOSアプリ版は自動起動）
ollama serve
```

### 3. モデルの取得

```bash
ollama pull qwen3:4b                # 取締役会の推論モデル（必須・約2.4GB）
ollama pull nomic-embed-text        # 意味検索を本物にする埋め込みモデル（任意・推奨）
```

`nomic-embed-text` を入れる場合は `config.yaml` の `retrieval.embedder` を `ollama` に変更する。
入れない場合は既定の `hashing`（オフライン・字句ベース）のまま動作する。

### 4. 接続確認

```bash
python main.py --health-check       # Status: OK が出れば準備完了
```

### 5. （任意）Letta 長期記憶サーバー

既定の長期記憶はローカルJSON（`storage/memory.json`）で完結するため不要。
Lettaサーバーを使う場合のみ `pip install letta-client` と Letta サーバーを用意し、
`config.yaml` の `memory.provider` を `letta` にして `letta_base_url` / `letta_agent_id` を設定する。

### トラブルシュート

| 症状 | 対処 |
|------|------|
| `--health-check` が FAIL | `ollama serve` が起動しているか、`base_url` が合っているか確認 |
| 会議が `model not found` | `ollama pull qwen3:4b` を実行したか確認 |
| 取り込み/検索が遅い・重い | `embedder: hashing`（既定）はモデル不要で軽い。意味検索品質を上げたい時だけ `ollama` に |
| telemetry のタイムアウト | `CREWAI_DISABLE_TELEMETRY=true`（`main.py` が自動設定済み） |

## 使い方

```bash
# 1. 知識ベースに取り込む（.txt/.md と関係グラフ記法を含む）
python main.py --ingest ./knowledge

# 2. 長期記憶に方針・禁止事項を登録する
python main.py --remember "ギャンブル・アダルト関連事業への参入禁止" --category 禁止事項
python main.py --memories            # 登録済みの記憶を一覧表示

# 3. 取締役会を開催する
python main.py "新規事業として、AIを活用した医療診断支援サービスを日本市場で展開したい。初期投資5億円、3年でのROI達成が目標。取締役会の判断を仰ぎたい。"

# その他
python main.py --health-check        # Ollama 接続確認
python main.py --no-rag "課題"       # RAG検索を無効化
python main.py --no-memory "課題"    # 長期記憶を無効化
python main.py --verbose "課題"      # CrewAI の詳細ログ
```

出力は5つのパネル（CFO財務分析 → CLO法務 → CEO草稿 → 監査役 → CEO最終）で表示され、`./outputs/meeting_*.json` に保存される。

## 関係グラフの記法

知識ファイルの中に、通常の文章と混在させて1行ずつ記述する（記法行のみがグラフに取り込まれる）。

```
顧客メディカル社 -[締結]-> 診断支援SaaS利用契約
診断支援SaaS利用契約 -[準拠]-> 薬機法
薬機法 -[所管]-> PMDA
```

「顧客メディカル社」を尋ねると、ベクトル検索では届かない「薬機法」「PMDA」まで関係連鎖で辿る。

## 設定（`config.yaml`）

| セクション | 主なキー | 説明 |
|-----------|---------|------|
| `brain` | `provider` | `ollama` / `openai_compatible` / `anthropic` / `stub` |
| | `model` | Ollamaモデルタグ、または `claude-...` |
| `retrieval` | `embedder` | `hashing`（オフライン）/ `ollama`（要embeddingモデル） |
| | `graph_enabled`, `graph_max_hops` | GraphRAGの有効化とホップ数 |
| `memory` | `provider` | `local`（JSON永続化）/ `letta`（要Lettaサーバー） |

### モデル交換

`brain.provider` を切り替えるだけでバックエンドを差し替えられる。Ollamaが使えない環境では `anthropic` を選び、`.env` に `ANTHROPIC_API_KEY` を設定する。

```yaml
brain:
  provider: anthropic
  model: claude-sonnet-4-6
```

## 開発フェーズ

- [x] **Phase 1** — 取締役会（Ollama + Qwen3-4B + CrewAI）
- [x] **Phase 2** — RAG統合（Qdrant + BM25 + RRF）
- [x] **Phase 3** — 長期記憶（Memory Loader + 書き戻し / Lettaアダプタ）
- [x] **Phase 4** — 企業知識グラフ（GraphRAG 関係性探索）
- [~] **Phase 5** — 共有SSM脳（TTT-Mamba）への置換 ※接続層は実装済み・モデル差し込み待ち

## Phase 5: 共有SSM脳（TTT-Mamba）への置換

設計思想「モデルは交換可能」により、**アプリ側のコード変更はゼロ**で、
`config.yaml` の `brain` セクションを切り替えるだけでモデルを差し替えられる。
難所は「TTT-Mamba をどう推論可能にするか」という外部のモデル準備に集約される。

### ルートA: GGUF を入手して Ollama に登録（最も手軽）

TTT-Mamba の GGUF が手に入る場合、新規コードは不要。

```bash
# Modelfile を用意（例）
cat > Modelfile <<'EOT'
FROM ./ttt-mamba-3b.gguf
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
EOT

ollama create ttt-mamba -f Modelfile
```

`config.yaml` は `provider: ollama` のまま `model: ttt-mamba` にするだけ。

### ルートB: vLLM / llama.cpp server で OpenAI 互換配信

GGUF以外の重み（HF形式など）や、より高速な推論をしたい場合。

```bash
# 例: vLLM で OpenAI 互換サーバーを起動
vllm serve <ttt-mamba-model-path> --port 8000
# あるいは llama.cpp: ./llama-server -m ttt-mamba.gguf --port 8000
```

`config.yaml`:

```yaml
brain:
  provider: openai_compatible
  model: ttt-mamba-3b           # サーバーが公開するモデル名
  base_url: http://localhost:8000/v1
```

接続層（`OpenAICompatibleProvider`）は実装・テスト済みで、認証が要るサーバーは
`.env` の `TITANS_LLM_API_KEY` で対応する。確認は `python main.py --health-check`。

### 現状の注意

TTT-Mamba は研究モデルで、`ollama pull` 一発で入る安定した配布形態がまだ無い。
本リポジトリで用意済みなのは「モデルが手に入った後に差し込む接続層」までであり、
モデル重み自体の入手・量子化は利用者側の作業になる。

## テスト

```bash
python -m pytest tests/ -q
```

埋め込みとLLMを使わないオフライン経路（`hashing` embedder、`stub`/モックLLM）で全テストが完結するため、モデル未取得の環境でも実行できる。

## ライセンス

MIT
