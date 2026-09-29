# dotfiles

macOS 用の個人設定。Ghostty / fish / tmux / starship / mise / git / vim / zsh。

## セットアップ

```sh
git clone https://github.com/sanojimaru/dotfiles ~/dotfiles
cd ~/dotfiles
brew bundle          # パッケージ導入
./install.sh         # ~ へシンボリックリンク (既存ファイルは ~/.dotfiles_backup へ退避)
```

## 構成

- `home/` — ホーム直下 (`.zshrc` `.zshenv` `.gitconfig` `.vimrc`)
- `config/` — `~/.config` 配下 (ghostty, fish, tmux, starship, git, mise)
- `Brewfile` — brew / cask / VS Code 拡張

## 管理しないもの

API キー等は `~/.env` に置き、リポジトリには含めない。
`.zshenv` と `config.fish` が起動時に読み込む。`.ssh` `.aws` `.npmrc` なども対象外。

## メモ

- テーマは Solarized Dark (Ghostty: `iTerm2 Solarized Dark`)。
- tmux の prefix は `C-a`。設定は `~/.config/tmux/tmux.conf`。
