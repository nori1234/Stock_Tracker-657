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

## セットアップ

```bash
pip install -r requirements.txt

# ローカルLLM（推奨・本筋の構成）
ollama pull qwen3:4b
```

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
| `brain` | `provider` | `ollama` / `anthropic` / `stub` |
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
- [ ] **Phase 5** — 共有SSM脳（TTT-Mamba）への置換 ※`BrainProvider`実装の追加のみ

## テスト

```bash
python -m pytest tests/ -q
```

埋め込みとLLMを使わないオフライン経路（`hashing` embedder、`stub`/モックLLM）で全テストが完結するため、モデル未取得の環境でも実行できる。

## ライセンス

MIT
