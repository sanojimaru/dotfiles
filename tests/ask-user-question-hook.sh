#!/usr/bin/env bash
# claude/hooks/block-heavy-ask-user-question.sh のテスト。
# 実行: tests/ask-user-question-hook.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
check() { # check <説明> <期待する値> <実際の値>
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (期待 $2, 実際 $3)"; fail=1; fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
expected='AskUserQuestion は推奨しません。質問は、基本的に返事の本文で、背景・選択肢ごとの中身・選んだときに起きること・おすすめとその理由を書いてから聞いてください。
AskUserQuestion を使ってよいのは、背景の説明が無くても答えられる軽い確認を、1 回 1 問で聞くときだけです。'

run() { # run <説明> <期待する終了コード> <tool_input.questions の JSON>
  local rc=0 out
  out=$(jq -cn --argjson questions "$3" '{tool_input:{questions:$questions}}' |
    "$ROOT/claude/hooks/block-heavy-ask-user-question.sh" 2>"$tmp/stderr") || rc=$?
  check "$1: 終了コード" "$2" "$rc"
  check "$1: 標準出力は空" "" "$out"
  if [ "$2" = 2 ]; then
    check "$1: 標準エラーは合意済みの文面" "$expected" "$(cat "$tmp/stderr")"
  else
    check "$1: 標準エラーは空" "" "$(cat "$tmp/stderr")"
  fi
}

run "2 問で止まる" 2 '[{"question":"進めてよいですか","options":[{"label":"はい"}]},{"question":"どの名前にしますか","options":[{"label":"A"}]}]'
run "preview があると止まる" 2 '[{"question":"どの名前にしますか","options":[{"label":"A"},{"label":"B","preview":"背景と選択肢の中身"}]}]'
run "空の preview でも止まる" 2 '[{"question":"進めてよいですか","options":[{"label":"はい","preview":""}]}]'
run "null の preview でも止まる" 2 '[{"question":"進めてよいですか","options":[{"label":"はい","preview":null}]}]'
run "1 問で preview なしは通る" 0 '[{"question":"進めてよいですか","options":[{"label":"はい"},{"label":"いいえ"}]}]'

exit "$fail"
