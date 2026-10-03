# ~/.env (API キー等。リポジトリ管理外) を読み込む — zsh の .zshenv と同等
if test -f $HOME/.env
    for line in (string match -rv '^\s*(#|$)' < $HOME/.env)
        set -l kv (string split -m1 = -- (string replace -r '^export\s+' '' -- $line))
        test (count $kv) -eq 2; and set -gx $kv[1] (string trim -c '"\'' -- $kv[2])
    end
end

# 環境変数・PATH（~/.zshenv から移植）
set -gx EDITOR vim
set -gx PNPM_HOME $HOME/Library/pnpm
set -gx ANDROID_HOME $HOME/Library/Android/sdk

fish_add_path -g $ANDROID_HOME/emulator $ANDROID_HOME/platform-tools
fish_add_path -g $PNPM_HOME $HOME/.dir/bin
# Rancher Desktop 同梱の docker / kubectl 等
fish_add_path -g $HOME/.rd/bin
fish_add_path -g /opt/homebrew/bin /opt/homebrew/sbin
fish_add_path -g $HOME/.local/share/mise/shims $HOME/.local/bin $HOME/.cargo/bin

# testcontainers (Node.js) は /var/run/docker.sock の存在チェックでしか docker を
# 自動検出しない。この symlink は Docker Desktop 用のパス(~/.docker/run/docker.sock、
# 存在しない)を指したままなので、Rancher Desktop 使用時は明示的に教える必要がある。
# Rancher Desktop の socket がある時だけ設定する(Docker Desktop に戻したときに
# 壊れないように)。
if test -S $HOME/.rd/docker.sock
    set -gx DOCKER_HOST unix://$HOME/.rd/docker.sock
    set -gx TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE /var/run/docker.sock
end

if status is-interactive
    set -g fish_greeting

    # ツール連携
    command -q starship; and starship init fish | source
    command -q zoxide;   and zoxide init fish | source
    command -q fzf;      and fzf --fish | source
    command -q direnv;   and direnv hook fish | source

    # エイリアス
    if command -q eza
        alias ls 'eza --icons --git'
        alias ll 'eza -la --icons --git'
        alias lt 'eza -T -L2 --icons --git'
    else
        alias ll 'ls -la'
    end
    command -q bat; and alias cat 'bat --paging=never'
    alias vi vim
    alias g git
    alias t 'tmux new-session -A -s main'

    # fzf は fd を使って高速に
    set -gx FZF_DEFAULT_COMMAND 'fd --type f --hidden --exclude .git'
    set -gx FZF_CTRL_T_COMMAND $FZF_DEFAULT_COMMAND
    set -gx FZF_DEFAULT_OPTS '--height 40% --layout=reverse --border'
end
