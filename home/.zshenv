# default API keys (OpenAI/Anthropic/Jev)
[ -f "$HOME/.env" ] && set -a && source "$HOME/.env" && set +a

# homebrew
export PATH=/opt/homebrew/bin:$PATH
eval "$(brew shellenv)"

# pkg-config
export PKG_CONFIG_PATH="/opt/homebrew/opt/icu4c/lib/pkgconfig"

# icu
export LDFLAGS="-L/opt/homebrew/opt/icu4c@76/lib"
export CPPFLAGS="-I/opt/homebrew/opt/icu4c@76/include"

# asdf (無効化: mise に移行)
# . /opt/homebrew/opt/asdf/libexec/asdf.sh

# mise
 eval "$(mise activate zsh)"
# mise shims (activate は precmd フックのためインタラクティブでない1回限りのシェル実行では
# PATH が更新されない。非対話実行でも .tool-versions/mise.toml のバージョンを解決できるよう
# shims も PATH に追加する)
export PATH="$HOME/.local/share/mise/shims:$PATH"

# direnv
eval "$(direnv hook zsh)"

# google cloud sdk
source '/opt/homebrew/share/google-cloud-sdk/completion.zsh.inc'
source '/opt/homebrew/share/google-cloud-sdk/path.zsh.inc'

# uv
export PATH="/Users/sanojimaru/.local/bin:$PATH"

# android sdk
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"


. "$HOME/.cargo/env"
