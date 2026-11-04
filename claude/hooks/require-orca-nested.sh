#!/bin/bash
# PreToolUse (Bash) フック: Orca の中で claude -p・codex exec を orca-nested なしで起動するのを止める。
set -u
[ -n "${ORCA_PANE_KEY-}" ] || exit 0
cmd=$(jq -r '.tool_input.command // empty')
# ; & | 改行で区切ったコマンドごとに、入れ子の起動があって orca-nested が無いかを見る
printf '%s\n' "$cmd" | tr ';&|' '\n\n\n' |
  grep -E '(^|[(`[:space:]])(claude[[:space:]]([^[:space:]]+[[:space:]]+)*(-p|--print)|codex[[:space:]]+exec)([[:space:]]|$)' |
  grep -vq 'orca-nested' || exit 0
echo "入れ子の claude -p・codex exec は orca-nested を付けて実行して (例: orca-nested claude -p \"...\")。ORCA_ の環境変数を受け継ぐと、入れ子の終わりを Orca がワーカーのターンの終わりと取り違えるから。" >&2
exit 2
