#!/usr/bin/env bash
# claude/hooks/require-orca-nested.sh のテスト。
# 実行: tests/session-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
check() { # check <説明> <期待する値> <実際の値>
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (期待 $2, 実際 $3)"; fail=1; fi
}

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
