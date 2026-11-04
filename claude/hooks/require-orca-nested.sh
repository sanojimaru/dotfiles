#!/bin/bash
# PreToolUse (Bash) フック: Orca の中で claude -p・codex exec を orca-nested なしで起動するのを止める。
set -u
[ -n "${ORCA_PANE_KEY-}" ] || exit 0
command -v jq >/dev/null || { echo "jq が無いので require-orca-nested.sh が効いていない" >&2; exit 1; }
cmd=$(jq -r '.tool_input.command // empty')
# 行末の \ の折り返しをつなぎ、起動ではない文字列 (ヒアドキュメントの本文・引用符の中。コミットメッセージなど。"$(...)" は残す) を消してから、
# ; & | 改行で区切ったコマンドごとに、入れ子の起動があって orca-nested が無いかを見る
printf '%s\n' "$cmd" | perl -0777 -pe '
  s/\\\n//g;
  s/<<-?[ \t]*([\x27"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?:\n|\z)/\n/gs;
  s/("(?:\\.|[^"\\])*")/my $q = $1; $q =~ m{\$\(|`} ? $q : ""/gse;
  s/\x27[^\x27]*\x27//g;
' | tr ';&|' '\n\n\n' |
  grep -E '(^|[(`[:space:]])(claude[[:space:]]([^[:space:]]+[[:space:]]+)*(-p|--print)|codex[[:space:]]+exec)([[:space:]]|$)' |
  grep -vq 'orca-nested' || exit 0
echo "入れ子の claude -p・codex exec は orca-nested を付けて実行して (例: orca-nested claude -p \"...\")。ORCA_ の環境変数を受け継ぐと、入れ子の終わりを Orca がワーカーのターンの終わりと取り違えるから。" >&2
exit 2
