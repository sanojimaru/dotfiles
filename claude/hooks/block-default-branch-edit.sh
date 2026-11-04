#!/bin/bash
# PreToolUse (Edit|Write|NotebookEdit) フック: 既定のブランチの作業ツリーにあるファイルの変更を止める。
set -u
path=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')
[ -n "$path" ] || exit 0
[ -e "$path" ] && path=$(realpath "$path") # ~/.claude/CLAUDE.md など、リンク先のリポジトリで判定する
dir=$(dirname "$path")
while [ ! -d "$dir" ]; do dir=$(dirname "$dir"); done
branch=$(git -C "$dir" symbolic-ref --short -q HEAD 2>/dev/null) || exit 0
default=$(git -C "$dir" symbolic-ref --short -q refs/remotes/origin/HEAD 2>/dev/null) || default=origin/main
[ "$branch" = "${default#origin/}" ] || exit 0
git -C "$dir" check-ignore -q "$path" 2>/dev/null && exit 0
echo "既定のブランチ ($branch) の作業ツリーではファイルを変えない。Issue を立て、orca worktree create --issue <番号> --agent <エージェント> --prompt <メモ> で別の worktree のセッションに渡して。既定のブランチに変更が残ると、worktree の作成や git pull の邪魔になるから。" >&2
exit 2
