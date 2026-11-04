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

# require-orca-nested
bash_json() { jq -cn --arg c "$1" '{tool_input:{command:$c}}'; }
export ORCA_PANE_KEY=x
check "Orca の中の claude -p を止める"      2 "$(run require-orca-nested.sh "$(bash_json 'cd a && claude -p "hi"')")"
check "--print も止める"                    2 "$(run require-orca-nested.sh "$(bash_json 'claude --print "hi"')")"
check "Orca の中の codex exec を止める"     2 "$(run require-orca-nested.sh "$(bash_json 'codex exec "hi"')")"
check "フラグの後ろの -p も止める"          2 "$(run require-orca-nested.sh "$(bash_json 'claude --model sonnet -p "hi"')")"
check "\$(...) の中も止める"                2 "$(run require-orca-nested.sh "$(bash_json 'x=$(claude -p hi)')")"
check "引用符の中の \$(...) も止める"       2 "$(run require-orca-nested.sh "$(bash_json 'out="$(claude -p hi)"')")"
check "env を前に付けても止める"            2 "$(run require-orca-nested.sh "$(bash_json 'env FOO=1 claude -p hi')")"
check "2 行目の起動も止める"                2 "$(run require-orca-nested.sh "$(bash_json $'echo a\nclaude -p hi')")"
check "\\ で折り返した起動も止める"         2 "$(run require-orca-nested.sh "$(bash_json $'claude --model sonnet \\\n  -p "hi"')")"
check "ヒアドキュメントを流し込む起動も止める" 2 "$(run require-orca-nested.sh "$(bash_json $'cat <<\'EOF\' | claude -p\nreview\nEOF')")"
check "' の中の \" に引きずられず止める"   2 "$(run require-orca-nested.sh "$(bash_json $'tr -d \'"\' < f; codex exec "review"')")"
check "付いていない方の起動を止める"        2 "$(run require-orca-nested.sh "$(bash_json 'orca-nested claude -p "a"; claude -p "b"')")"
check "orca-nested 付きは通す"              0 "$(run require-orca-nested.sh "$(bash_json 'orca-nested claude -p "hi"')")"
check "\\ で折り返した orca-nested は通す"  0 "$(run require-orca-nested.sh "$(bash_json $'orca-nested \\\n  claude -p "hi"')")"
check "引用符の中の claude -p は通す"       0 "$(run require-orca-nested.sh "$(bash_json 'git commit -m "hook: claude -p を止める"')")"
check "ヒアドキュメントの中は通す"          0 "$(run require-orca-nested.sh "$(bash_json $'git commit -F - <<\'EOF\'\nhook: claude -p を止める\nEOF')")"
check "対話の claude は通す"                0 "$(run require-orca-nested.sh "$(bash_json 'claude --version')")"
unset ORCA_PANE_KEY
check "Orca の外は通す"                     0 "$(run require-orca-nested.sh "$(bash_json 'claude -p "hi"')")"

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
