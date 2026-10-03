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

for f in .zshrc .zshenv .gitconfig .vimrc; do link "home/$f" "$HOME/$f"; done
link config/ghostty/config     "$HOME/.config/ghostty/config"
link config/fish/config.fish   "$HOME/.config/fish/config.fish"
link config/tmux/tmux.conf     "$HOME/.config/tmux/tmux.conf"
link config/starship.toml      "$HOME/.config/starship.toml"
link config/git/ignore         "$HOME/.config/git/ignore"
link config/mise/config.toml   "$HOME/.config/mise/config.toml"

# VS Code (パスに空白を含むので必ず引用)
VSCODE="$HOME/Library/Application Support/Code/User"
for f in settings.json keybindings.json mcp.json; do link "vscode/$f" "$VSCODE/$f"; done

# Claude Code / Codex (設定の実体だけ。認証情報・履歴は対象外)
# 全体指示は 1 ファイルを両方へ (Claude は全体指示としての AGENTS.md を読まないため CLAUDE.md の名前でリンク)
link agents/AGENTS.md                     "$HOME/.claude/CLAUDE.md"
link agents/AGENTS.md                     "$HOME/.codex/AGENTS.md"
link claude/hooks/worktree-branch-cleanup.sh "$HOME/.claude/hooks/worktree-branch-cleanup.sh"
link codex/keybindings.json               "$HOME/.codex/keybindings.json"
for s in proposal-slide-design-markdown proposal-slide-image-deck; do
  link "codex/skills/$s" "$HOME/.codex/skills/$s"
done

echo "完了。パッケージは: brew bundle --file=$ROOT/Brewfile"
