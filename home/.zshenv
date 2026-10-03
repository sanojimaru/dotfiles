# 環境変数と PATH のみ (対話用の設定は .zshrc)。fish 側は config/fish/config.fish に同等の設定がある。

# ~/.env (API キー等。リポジトリ管理外)
[ -f "$HOME/.env" ] && { set -a; . "$HOME/.env"; set +a; }

export EDITOR=vim
export PNPM_HOME="$HOME/Library/pnpm"
export ANDROID_HOME="$HOME/Library/Android/sdk"

eval "$(/opt/homebrew/bin/brew shellenv)"

# mise は shims 方式 (非対話シェルでもバージョンが解決される)
export PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:$HOME/.dir/bin:$PNPM_HOME:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

# Rancher Desktop 同梱の docker / kubectl 等
export PATH="$PATH:$HOME/.rd/bin"

# testcontainers (Node.js) は /var/run/docker.sock の存在チェックでしか docker を
# 自動検出しない。この symlink は Docker Desktop 用のパス(~/.docker/run/docker.sock、
# 存在しない)を指したままなので、Rancher Desktop 使用時は明示的に教える必要がある。
# Rancher Desktop の socket がある時だけ設定する(Docker Desktop に戻したときに
# 壊れないように)。
if [ -S "$HOME/.rd/docker.sock" ]; then
  export DOCKER_HOST="unix://$HOME/.rd/docker.sock"
  export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE="/var/run/docker.sock"
fi

[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
