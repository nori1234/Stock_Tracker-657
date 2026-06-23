#!/usr/bin/env bash
# PostToolUse フック: GitHub の PR マージ (mcp__github__merge_pull_request) 成功後、
# 現在のフィーチャーブランチを最新 origin/main へ再同期する。
#
# 目的: squash マージ後も同じブランチに commit を積み続けると履歴が分岐し、
# 次の PR でマージコンフリクトになる。マージ直後はブランチ内容が main と
# 一致しているので、ここでブランチ ref を origin/main へ進めておけば、
# 以降の commit はクリーンに main の上へ積み上がる。
#
# 安全策: 作業ツリーが汚れている / main 上 / detached HEAD のときは何もしない。
set -u

# stdin の JSON は読み捨て (tool_response の成否までは見ず、マージ成功時のみ
# 呼ばれる PostToolUse 前提)。
cat >/dev/null 2>&1 || true

# git リポジトリ外なら無視
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ "$branch" = "main" ] || [ "$branch" = "HEAD" ] || [ -z "$branch" ]; then
  exit 0
fi

# 未コミット変更があるブランチは触らない (取りこぼし防止)
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  printf '{"systemMessage":"マージ後の自動同期をスキップ: 作業ツリーに未コミット変更があります"}\n'
  exit 0
fi

if ! git fetch origin main --quiet 2>/dev/null; then
  exit 0
fi

before=$(git rev-parse HEAD 2>/dev/null)
target=$(git rev-parse origin/main 2>/dev/null)
if [ "$before" = "$target" ]; then
  exit 0   # 既に main 上 (再同期不要)
fi

if git reset --hard origin/main --quiet 2>/dev/null; then
  printf '{"systemMessage":"ブランチ %s を origin/main に再同期しました (squashマージ後の履歴分岐を防止)。以降の commit はクリーンに積み上がります。"}\n' "$branch"
fi
exit 0
