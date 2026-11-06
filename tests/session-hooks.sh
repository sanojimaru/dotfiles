#!/usr/bin/env bash
# bin/orca-nested と claude/hooks の PreToolUse フック 2 つのテスト。
# 実行: tests/session-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0
check() { # check <説明> <期待する値> <実際の値>
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (期待 $2, 実際 $3)"; fail=1; fi
}
run() { # run <フック> <stdin の JSON>  → 終了コードを出す
  local rc=0; printf '%s' "$2" | "$ROOT/claude/hooks/$1" 2>/dev/null || rc=$?; echo "$rc"
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

# block-default-branch-edit
git init -q -b main "$WORK/repo"
git -C "$WORK/repo" commit -q --allow-empty --no-gpg-sign -m init
printf 'ignored.txt\n' > "$WORK/repo/.gitignore"
edit_json() { jq -cn --arg p "$1" '{tool_input:{file_path:$p}}'; }
check "既定のブランチのファイルを止める"   2 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/a.txt")")"
check "notebook_path も止める"             2 "$(run block-default-branch-edit.sh "$(jq -cn --arg p "$WORK/repo/a.ipynb" '{tool_input:{notebook_path:$p}}')")"
check "まだ無いディレクトリでも止める"     2 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/new/dir/a.txt")")"
check "gitignore されたファイルは通す"     0 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/ignored.txt")")"
ln -s "$WORK/repo/a.txt" "$WORK/link.txt"; touch "$WORK/repo/a.txt"
check "リンク先が既定のブランチなら止める" 2 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/link.txt")")"
check "リポジトリの外は通す"               0 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/a.txt")")"
git -C "$WORK/repo" switch -q -c feature
check "作業用ブランチは通す"               0 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/repo/a.txt")")"
git init -q -b master "$WORK/legacy"
check "origin/HEAD が無ければ master も止める" 2 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/legacy/a.txt")")"
git -C "$WORK/legacy" commit -q --allow-empty --no-gpg-sign -m init
git clone -q "$WORK/legacy" "$WORK/clone"
check "origin/HEAD が指す既定のブランチを止める" 2 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/clone/a.txt")")"
git -C "$WORK/clone" switch -q -c main
check "origin/HEAD が master なら main は通す" 0 "$(run block-default-branch-edit.sh "$(edit_json "$WORK/clone/a.txt")")"

exit "$fail"
