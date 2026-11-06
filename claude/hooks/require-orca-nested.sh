#!/bin/bash
# PreToolUse (Bash) フック: Orca の中で orca-nested なしの claude -p・codex exec を見つけたら、止めずに Claude へ警告する。
# 文字列で見るだけなので、メッセージの中の "claude -p" にも反応する。止めないので実害は無い。
set -u
[ -n "${ORCA_PANE_KEY-}" ] || exit 0
command -v jq >/dev/null || { echo "jq が無いので require-orca-nested.sh が効いていない" >&2; exit 1; }
cmd=$(jq -r '.tool_input.command // empty')
printf '%s' "$cmd" | grep -Eq 'claude[^;&|]*[[:space:]](-p|--print)([[:space:]]|$)|codex[[:space:]]+exec' || exit 0
printf '%s' "$cmd" | grep -q 'orca-nested' && exit 0
jq -cn '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext:
  "入れ子の claude -p・codex exec は orca-nested を付けて実行して (例: orca-nested claude -p \"...\")。ORCA_ の環境変数を受け継ぐと、入れ子の終わりを Orca がワーカーのターンの終わりと取り違えるから。ただの文字列なら無視してよい。"}}'
