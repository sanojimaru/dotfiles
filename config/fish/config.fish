# ~/.env (API キー等。リポジトリ管理外) を読み込む — zsh の .zshenv と同等
if test -f $HOME/.env
    for line in (string match -rv '^\s*(#|$)' < $HOME/.env)
        set -l kv (string split -m1 = -- (string replace -r '^export\s+' '' -- $line))
        # 値を囲む引用符 (op-env はシングルクォートで書く) を1組だけ外す
        test (count $kv) -eq 2; and set -gx $kv[1] (string replace -r '^([\'"])(.*)\1$' '$2' -- $kv[2])
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
