#!/usr/bin/env bash
# bin/orca-nested と claude/hooks の PreToolUse フック 2 つのテスト。
# 実行: tests/session-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0
check() { # check <説明> <期待する終了コード> <実際の終了コード>
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (期待 $2, 実際 $3)"; fail=1; fi
}
run() { # run <フック> <stdin の JSON>  → 終了コードを出す
  local rc=0; printf '%s' "$2" | "$ROOT/claude/hooks/$1" 2>/dev/null || rc=$?; echo "$rc"
}

# orca-nested: ORCA_ だけを外す
out=$(ORCA_PANE_KEY=x KEEP_ME=y "$ROOT/bin/orca-nested" env)
echo "$out" | grep -q '^ORCA_' && rc=1 || rc=0; check "orca-nested は ORCA_ を外す" 0 "$rc"
echo "$out" | grep -q '^KEEP_ME=y$' && rc=0 || rc=1; check "orca-nested はほかの変数を残す" 0 "$rc"

# require-orca-nested
bash_json() { jq -cn --arg c "$1" '{tool_input:{command:$c}}'; }
export ORCA_PANE_KEY=x
check "Orca の中の claude -p を止める"      2 "$(run require-orca-nested.sh "$(bash_json 'cd a && claude -p "hi"')")"
check "Orca の中の codex exec を止める"     2 "$(run require-orca-nested.sh "$(bash_json 'codex exec "hi"')")"
check "orca-nested 付きは通す"             0 "$(run require-orca-nested.sh "$(bash_json 'orca-nested claude -p "hi"')")"
check "文字列の中の claude -p は通す"      0 "$(run require-orca-nested.sh "$(bash_json "grep 'claude -p' f")")"
check "対話の claude は通す"               0 "$(run require-orca-nested.sh "$(bash_json 'claude --version')")"
unset ORCA_PANE_KEY
check "Orca の外は通す"                    0 "$(run require-orca-nested.sh "$(bash_json 'claude -p "hi"')")"

# block-default-branch-edit
git init -q -b main "$WORK/repo"
git -C "$WORK/repo" commit -q --allow-empty -m init
printf 'ignored.txt\n' > "$WORK/repo/.gitignore"
edit_json() { jq -cn --arg p "$1" '{tool_input:{file_path:$p}}'; }
check "既定のブランチのファイルを止める"   2 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/a.txt")")"
check "まだ無いディレクトリでも止める"     2 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/new/dir/a.txt")")"
check "gitignore されたファイルは通す"     0 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/ignored.txt")")"
check "リポジトリの外は通す"               0 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/a.txt")")"
git -C "$WORK/repo" switch -q -c feature
check "作業用ブランチは通す"               0 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/a.txt")")"

exit "$fail"
