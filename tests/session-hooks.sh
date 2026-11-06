#!/usr/bin/env bash
# bin/orca-nested と claude/hooks/require-orca-nested.sh のテスト。
# 実行: tests/session-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
check() { # check <説明> <期待する値> <実際の値>
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (期待 $2, 実際 $3)"; fail=1; fi
}

# orca-nested: ORCA_ だけを外し、引数と終了コードはそのまま渡す
out=$(ORCA_PANE_KEY=x KEEP_ME=y "$ROOT/bin/orca-nested" env)
echo "$out" | grep -q '^ORCA_' && rc=1 || rc=0; check "orca-nested は ORCA_ を外す" 0 "$rc"
echo "$out" | grep -q '^KEEP_ME=y$' && rc=0 || rc=1; check "orca-nested はほかの変数を残す" 0 "$rc"
rc=0; out=$("$ROOT/bin/orca-nested" sh -c 'printf "%s|" "$@"; exit 7' _ "a b" c) || rc=$?
check "orca-nested は空白を含む引数をそのまま渡す" "a b|c|" "$out"
check "orca-nested はコマンドの終了コードを返す" 7 "$rc"
rc=0; "$ROOT/bin/orca-nested" 2>/dev/null || rc=$?; check "orca-nested は引数なしで失敗する" 2 "$rc"

# require-orca-nested: 止めずに (exit 0)、警告を additionalContext で返す
warn() { # warn <コマンド>  → 警告を返したら warn、返さなければ none
  jq -cn --arg c "$1" '{tool_input:{command:$c}}' | "$ROOT/claude/hooks/require-orca-nested.sh" |
    jq -e '.hookSpecificOutput.additionalContext' >/dev/null 2>&1 && echo warn || echo none
}
export ORCA_PANE_KEY=x
check "claude -p に警告する"               warn "$(warn 'cd a && claude -p "hi"')"
check "フラグの後ろの -p にも警告する"     warn "$(warn 'claude --model sonnet -p "hi"')"
check "--print にも警告する"               warn "$(warn 'claude --print "hi"')"
check "codex exec にも警告する"            warn "$(warn 'codex exec "hi"')"
check "orca-nested 付きには警告しない"     none "$(warn 'orca-nested claude -p "hi"')"
check "対話の claude には警告しない"       none "$(warn 'claude --version')"
rc=0; echo '{"tool_input":{"command":"claude -p hi"}}' | "$ROOT/claude/hooks/require-orca-nested.sh" >/dev/null || rc=$?
check "止めない"                           0    "$rc"
unset ORCA_PANE_KEY
check "Orca の外では警告しない"            none "$(warn 'claude -p "hi"')"

exit "$fail"
