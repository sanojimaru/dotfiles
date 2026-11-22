#!/usr/bin/env bash
# dotfiles をホームへシンボリックリンクする。既存ファイルは ~/.dotfiles_backup へ退避。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKUP="$HOME/.dotfiles_backup/$(date +%Y%m%d-%H%M%S)"

link() { # link <repo内の相対パス> <リンク先の絶対パス>
  local src="$ROOT/$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then echo "ok      $dst"; return; fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    mkdir -p "$BACKUP"; mv "$dst" "$BACKUP/$(basename "$dst")"; echo "backup  $dst"
  fi
  ln -s "$src" "$dst"; echo "link    $dst"
}

copy() { # copy <repo内の相対パス> <配置先の絶対パス>。worktree を消しても動くよう実体を置く
  local src="$ROOT/$1" dst="$2" tmp
  mkdir -p "$(dirname "$dst")"
  tmp="$(mktemp "$(dirname "$dst")/.install.XXXXXX")"
  cp "$src" "$tmp" && chmod 755 "$tmp" && mv -f "$tmp" "$dst" || { rm -f "$tmp"; return 1; }
  echo "copy    $dst"
}

# 共通スキルは他のツールも管理する場所へ配るため、同名の既存スキルを退避・上書きしない。
# 全件を先に確かめ、衝突する名前があればリンクを変更する前に止める。
for skill in "$ROOT"/agents/skills/*; do
  [ -f "$skill/SKILL.md" ] || continue
  name="$(basename "$skill")"
  for legacy in "$ROOT/codex/skills/$name" "$HOME/.codex/skills/$name"; do
    if [ -e "$legacy" ] || [ -L "$legacy" ]; then
      echo "error   共通スキル $name が Codex 専用スキルと衝突: $legacy" >&2
      exit 1
    fi
  done
  for dst in "$HOME/.agents/skills/$name" "$HOME/.claude/skills/$name"; do
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$skill" ]; then continue; fi
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      echo "error   共通スキル $name の配置先が使用中: ${dst}（上書きしません）" >&2
      exit 1
    fi
  done
done

for f in .zshrc .zshenv .gitconfig .vimrc; do link "home/$f" "$HOME/$f"; done
link config/ghostty/config     "$HOME/.config/ghostty/config"
link config/fish/config.fish   "$HOME/.config/fish/config.fish"
link config/tmux/tmux.conf     "$HOME/.config/tmux/tmux.conf"
link config/starship.toml      "$HOME/.config/starship.toml"
link config/git/ignore         "$HOME/.config/git/ignore"
link config/mise/config.toml   "$HOME/.config/mise/config.toml"
link bin/op-env                "$HOME/.local/bin/op-env"
link bin/orca-nested           "$HOME/.local/bin/orca-nested"
# PATH で本物の codex（/opt/homebrew/bin）より前に置き、起動のたびに自分が管理するフックを信頼する
if [ -f "$HOME/.local/bin/codex" ] && [ ! -L "$HOME/.local/bin/codex" ]; then
  # 本物の codex を退避すると、ラッパーが起動する先を失うので置き換えない
  echo "skip    $HOME/.local/bin/codex（本物の codex がある。別の場所へ移してから再実行する）" >&2
else
  link bin/codex                "$HOME/.local/bin/codex"
fi
link bin/codex-hook-trust      "$HOME/.local/bin/codex-hook-trust"
copy bin/agent-usage           "$HOME/.local/bin/agent-usage"

# VS Code (パスに空白を含むので必ず引用)
VSCODE="$HOME/Library/Application Support/Code/User"
for f in settings.json keybindings.json mcp.json; do link "vscode/$f" "$VSCODE/$f"; done

# Claude Code / Codex (設定の実体だけ。認証情報・履歴は対象外)
# 全体指示は 1 ファイルを両方へ (Claude は全体指示としての AGENTS.md を読まないため CLAUDE.md の名前でリンク)
link agents/AGENTS.md                     "$HOME/.claude/CLAUDE.md"
link agents/AGENTS.md                     "$HOME/.codex/AGENTS.md"
link claude/hooks/worktree-branch-cleanup.sh "$HOME/.claude/hooks/worktree-branch-cleanup.sh"
link claude/hooks/require-orca-nested.sh "$HOME/.claude/hooks/require-orca-nested.sh"
link claude/hooks/block-heavy-ask-user-question.sh "$HOME/.claude/hooks/block-heavy-ask-user-question.sh"
link codex/keybindings.json               "$HOME/.codex/keybindings.json"
for s in proposal-slide-design-markdown proposal-slide-image-deck; do
  link "codex/skills/$s" "$HOME/.codex/skills/$s"
done
for skill in "$ROOT"/agents/skills/*; do
  [ -f "$skill/SKILL.md" ] || continue
  name="$(basename "$skill")"
  link "agents/skills/$name" "$HOME/.agents/skills/$name"
  link "agents/skills/$name" "$HOME/.claude/skills/$name"
done

echo "完了。パッケージは: brew bundle --file=$ROOT/Brewfile"
