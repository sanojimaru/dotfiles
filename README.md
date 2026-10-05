# dotfiles

macOS 用の個人設定。Ghostty / fish / tmux / starship / mise / git / vim / zsh。
新しい Mac でも、このページの手順どおりに進めれば同じ環境を再現できる。

## セットアップ手順

前提: macOS、Xcode Command Line Tools (`xcode-select --install`)。

```sh
# 1. Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. リポジトリ取得
git clone https://github.com/sanojimaru/dotfiles ~/dotfiles
cd ~/dotfiles

# 3. パッケージ導入 (下の一覧すべて)
brew bundle

# 4. 設定をホームへリンク (既存ファイルは ~/.dotfiles_backup へ退避)
./install.sh

# 5. 言語ランタイム/CLI (mise)
mise install

# 6. vim プラグイン (vim-plug)
curl -fLo ~/.vim/autoload/plug.vim --create-dirs https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
vim +PlugInstall +qall

# 7. ログインシェルを fish に
echo /opt/homebrew/bin/fish | sudo tee -a /etc/shells
chsh -s /opt/homebrew/bin/fish
```

手動で用意するもの: `~/.config/op/service-account-token` (下記「Service Account の準備」参照。`~/.env` もこれで作れる)、`gh auth login`、各クラウド CLI のログイン。

## 管理しているソフトウェア

正本は [`Brewfile`](Brewfile)。ここには用途別の要約を置く。

### ターミナル環境

| ソフト | 用途 | 設定ファイル |
|---|---|---|
| Ghostty (公式アプリを直接導入。brew 管理外) | ターミナル。Solarized Dark、fish 起動 | `config/ghostty/config` |
| fish | 普段使いのシェル (ログインシェル) | `config/fish/config.fish` |
| zsh | 互換用に維持 (`zsh-autosuggestions` `zsh-completions` 使用) | `home/.zshrc` `home/.zshenv` |
| tmux | 端末多重化。prefix は `C-a`、Solarized Dark | `config/tmux/tmux.conf` |
| starship | プロンプト | `config/starship.toml` |
| vim + vim-plug | エディタ。NERDTree / airline / fugitive | `home/.vimrc` |
| font-hack-nerd-font | ターミナルのフォント (アイコン用 Nerd Font) | |
| font-plemol-jp / font-ricty-diminished / font-powerline-symbols | 日本語・powerline 用の予備フォント | |

### コマンドラインツール

| 分類 | ソフト |
|---|---|
| 検索・表示 | ripgrep, fd, fzf, eza, bat, zoxide, cloc, poppler |
| Git | git, gh, gibo, git-filter-repo, subversion |
| ランタイム管理 | mise (`config/mise/config.toml`: direnv, golangci-lint, lefthook, task, websocat) |
| Python | python@3.13, uv, pipx |
| Java / ネイティブ | openjdk, icu4c@76, pkgconf, pango |
| ネットワーク | wget, tailscale, ngrok (cask) |
| データ・メディア | postgresql@18, ffmpeg, openai-whisper |
| 検証 | actionlint |

### クラウド・インフラ

awscli, aws-sam-cli, session-manager-plugin (cask), azure-cli, gcloud-cli (cask), firebase-cli, rancher (cask, Rancher Desktop: docker / docker compose / kubectl を同梱), kustomize, kube-score, skaffold, powershell

### iOS / Swift 開発

xcodegen, tuist (cask), swiftlint, swift-format, xcbeautify, xcode-build-server, ios-deploy

### AI ツール

claude (cask, デスクトップアプリ), claude-code (cask), codex (cask), gemini-cli, opencode

### その他アプリ

drawio (cask), libreoffice (cask)

## 構成

- `home/` — ホーム直下 (`.zshrc` `.zshenv` `.gitconfig` `.vimrc`)
- `config/` — `~/.config` 配下 (ghostty, fish, tmux, starship, git, mise)
- `bin/` — 自作コマンド (`~/.local/bin` へリンク。`op-env` は 1Password の Service Account でキーを `.env` に書く)
- `agents/AGENTS.md` — Claude Code と Codex 共通の全体指示 (`~/.claude/CLAUDE.md` と `~/.codex/AGENTS.md` へリンク)
- `claude/` — Claude Code のフック (`~/.claude` へリンク)
- `codex/` — Codex のキーバインド・自作スキル (`~/.codex` へリンク)
- `vscode/` — VS Code ユーザー設定 (`settings.json` `keybindings.json` `mcp.json`)
- `Brewfile` — brew / cask
- `install.sh` — シンボリックリンクの作成

## 管理しないもの

API キー等は `~/.env` に置き (`OPENAI_API_KEY` `ANTHROPIC_API_KEY` `TYPESAFE_API_KEY` `OBSIDIAN_MCP_API_KEY`)、リポジトリには含めない。
`.zshenv` と `config.fish` が起動時に読み込む。`.ssh` `.aws` `.npmrc` `.claude/.credentials.json` なども対象外。
プロジェクト固有のキーは 1Password の `Dev` vault に置き、エージェントが `op-env KEY...` (Service Account 経由) で各プロジェクトの `.env` に書き出す。`.env` は `mise.toml` の `[env] _.file = ".env"` で読み込み、グローバル gitignore で除外する (キー名だけの `.env.example` をコミット)。リモート作業では `op` の GUI 認証が通らないため Service Account を使う。

`~/.codex/.env` は GUI 版 codex が直接読むため残す (`OBSIDIAN_MCP_API_KEY` は両方に置く)。
`~/.claude/settings.json` と `~/.codex/config.toml` `~/.codex/hooks.json` は管理しない。Orca がフックや worktree の信頼設定を書き込み、Claude Code / Codex 自身も常時書き換えるため (各マシンで直接編集する)。
`~/.claude` の skills は、ツール管理か別リポジトリのリンクなので対象外。
`codex/skills/proposal-*` は社内向けの名称・ブランド素材を含む (意図して公開)。
`agents/AGENTS.md` はリポジトリが公開のため、API キー・トークン・社内固有名などを書かない。
各プロジェクトの指示は `AGENTS.md` だけを書けばよい (Claude Code も、プロジェクトに CLAUDE.md が無ければ AGENTS.md を読む)。

## Service Account の準備

エージェントが GUI 認証なしでキーを取り出すための準備。Mac の前で 1 回だけ行う。

1. 1Password に `Dev` vault を作り、エージェントに渡してよいキーを入れる (アイテム名は環境変数名、値はフィールド `credential`)。まず `ANTHROPIC_API_KEY` `OPENAI_API_KEY` `TYPESAFE_API_KEY` を入れる。Service Account は `Personal` vault を読めないため
2. `Dev` だけを読み取り専用で読める Service Account を作り、トークンを保存する (画面にもクリップボードにも出さない):
   `mkdir -p ~/.config/op && (umask 077; op service-account create agent --vault Dev:read_items --raw > ~/.config/op/service-account-token)`
3. 確認: `cd /tmp && op-env ANTHROPIC_API_KEY && cut -d= -f1 .env && rm .env`

`~/.env` も `cd ~ && op-env ANTHROPIC_API_KEY OPENAI_API_KEY TYPESAFE_API_KEY` で作り直せる (他のキーの行は残る)。
トークンが漏れたら、1Password で Service Account を削除して作り直す。

## メンテナンス

パッケージを入れたら Brewfile を更新する。

```sh
cd ~/dotfiles && brew bundle dump --force
```

設定ファイルはシンボリックリンクなので、`~` 側を編集すればそのままリポジトリに反映される。
