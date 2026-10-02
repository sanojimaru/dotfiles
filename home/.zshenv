# 環境変数と PATH のみ (対話用の設定は .zshrc)。fish 側は config/fish/config.fish に同等の設定がある。

# ~/.env (API キー等。リポジトリ管理外)
[ -f "$HOME/.env" ] && { set -a; . "$HOME/.env"; set +a; }

export EDITOR=vim
export PNPM_HOME="$HOME/Library/pnpm"
export ANDROID_HOME="$HOME/Library/Android/sdk"

eval "$(/opt/homebrew/bin/brew shellenv)"

# mise は shims 方式 (非対話シェルでもバージョンが解決される)
export PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:$HOME/.dir/bin:$PNPM_HOME:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
