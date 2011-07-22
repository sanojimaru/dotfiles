# Environment variable configuration
export LANG=en_US.UTF-8
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# OSにより端末を判定
case "${OSTYPE}" in
darwin*)
  alias ls="ls -lG -w"
  alias ks="ls"
  alias sl="ls"

  # ruby rvm
  [[ -s "$HOME/.rvm/scripts/rvm" ]] && source "$HOME/.rvm/scripts/rvm"

  # node nvm
  source $HOME/.nvm/nvm.sh

  # cakephp
  alias cake='$HOME/workspace/cakephp/cake/console/cake "$@"'

  # python
  #export WORKON_HOME=$HOME/.virtualenvs
  #source /usr/local/bin/virtualenvwrapper.sh
  #export PIP_DOWNLOAD_CACHE=~/.pip_cache
  #export PIP_REQUIRE_VIRTUALENV=true
  #export PIP_RESPECT_VIRTUALENV=true

  # android
  #export PATH=$PATH:$HOME/.android-sdk/apktool

  # vim
  export EDITOR=/Applications/MacVim.app/Contents/MacOS/Vim
  alias vim='/Applications/MacVim.app/Contents/MacOS/Vim -u $HOME/.vimrc "$@"'
  alias vi='vim'
  alias v='vim'
  alias gvim='open -a MacVim.app "$@"'
  alias gv='gvim'

  # emacs
  #alias emacs='/usr/local/Cellar/emacs/23.3/Emacs.app/Contents/MacOS/Emacs "$@"'
  alias emacs='$HOME/.emacs.d/emacs "$@"'
  alias e='emacs'
  ;;
linux*)
  alias ls="ls -l --color"
  alias "www-data"="sudo su - www-data -s /bin/bash"
  alias mysql="mysql -uroot -pzaq12wsxcde34rfv -hlocalhost"
  # ruby rvm
  [[ -s "$HOME/.rvm/scripts/rvm" ]] && source "$HOME/.rvm/scripts/rvm"
  ;;
esac

# Default shell configuration
autoload colors
colors
case ${UID} in
0)
    PROMPT="%B%{${fg[red]}%}%/#%{${reset_color}%}%b "
    PROMPT2="%B%{${fg[red]}%}%_#%{${reset_color}%}%b "
    SPROMPT="%B%{${fg[red]}%}%r is correct? [n,y,a,e]:%{${reset_color}%}%b "
    [ -n "${REMOTEHOST}${SSH_CONNECTION}" ] &&
        PROMPT="%{${fg[cyan]}%}$(echo ${HOST%%.*} | tr '[a-z]' '[A-Z]') ${PROMPT}"
    ;;
*)
  # Color
  DEFAULT=$'%{\e[1;0m%}'
  RESET="%{${reset_color}%}"
  GREEN="%{${fg[green]}%}"
  BLUE="%{${fg[blue]}%}"
  RED="%{${fg[red]}%}"
  CYAN="%{${fg[cyan]}%}"
  WHITE="%{${fg[white]}%}"
  ;;
esac

# terminal configuration
unset LSCOLORS

case "${TERM}" in
xterm|xterm-color|xterm-256color|screen|screen-256color)
    export LSCOLORS=exfxcxdxbxegedabagacad
    export LS_COLORS='di=34:ln=35:so=32:pi=33:ex=31:bd=46;34:cd=43;34:su=41;30:sg=46;30:tw=42;30:ow=43;30'
    zstyle ':completion:*' list-colors 'di=34' 'ln=35' 'so=32' 'ex=31' 'bd=46;34' 'cd=43;34'

     precmd() {
        echo -ne "\033]0;${USER}@${HOST%%.*}:${PWD}\007"
    }
    ;;
esac

# Prompt
setopt prompt_subst
PROMPT='${RESET}${GREEN}${WINDOW:+"[$WINDOW]"}${RESET}%{$fg_bold[blue]%}${USER}@%m ${RESET}${WHITE}$ ${RESET}'
RPROMPT='${RESET}${WHITE}%1(v|%F{green}%1v%f|) [${BLUE}%(5~,%-2~/.../%2~,%~)% ${WHITE}] ${RESET}'

# vcs_info
autoload -Uz add-zsh-hook
autoload -Uz vcs_info
zstyle ':vcs_info:*' enable git svn hg bzr
zstyle ':vcs_info:*' formats '(%s)-[%b]'
zstyle ':vcs_info:*' actionformats '(%s)-[%b|%a]'
zstyle ':vcs_info:(svn|bzr):*' branchformat '%b:r%r'
zstyle ':vcs_info:bzr:*' use-simple true

autoload -Uz is-at-least
if is-at-least 4.3.10; then
  # この check-for-changes が今回の設定するところ
  zstyle ':vcs_info:git:*' check-for-changes true
  zstyle ':vcs_info:git:*' stagedstr "+"    # 適当な文字列に変更する
  zstyle ':vcs_info:git:*' unstagedstr "-"  # 適当の文字列に変更する
  zstyle ':vcs_info:git:*' formats '(%s)-[%b] %c%u'
  zstyle ':vcs_info:git:*' actionformats '(%s)-[%b|%a] %c%u'
fi

function _update_vcs_info_msg() {
    psvar=()
    LANG=en_US.UTF-8 vcs_info
    [[ -n "$vcs_info_msg_0_" ]] && psvar[1]="$vcs_info_msg_0_"
}
add-zsh-hook precmd _update_vcs_info_msg

# 指定したコマンド名がなく、ディレクトリ名と一致した場合 cd する
setopt auto_cd

# cd でTabを押すとdir list を表示
setopt auto_pushd

# ディレクトリスタックに同じディレクトリを追加しないようになる
setopt pushd_ignore_dups

# 上書きリダイレクトの禁止
setopt no_clobber

# 補完候補リストを詰めて表示
setopt list_packed

# auto_list の補完候補一覧で、ls -F のようにファイルの種別をマーク表示
setopt list_types

# 補完候補が複数ある時に、一覧表示する
setopt auto_list

# コマンドラインの引数で --prefix=/usr などの = 以降でも補完できる
setopt magic_equal_subst

# カッコの対応などを自動的に補完する
setopt auto_param_keys

# ディレクトリ名の補完で末尾の / を自動的に付加し、次の補完に備える
setopt auto_param_slash

# 補完キー（Tab,  Ctrl+I) を連打するだけで順に補完候補を自動で補完する
setopt auto_menu

# sudoも補完の対象
zstyle ':completion:*:sudo:*' command-path /usr/local/sbin /usr/local/bin /usr/sbin /usr/bin /sbin /bin

# 色付きで補完する
zstyle ':completion:*' list-colors di=34 fi=0
#zstyle ':completion:*' list-colors ${(s.:.)LS_COLORS}

# 複数のリダイレクトやパイプなど、必要に応じて tee や cat の機能が使われる
setopt multios

# beepを鳴らさないようにする
setopt nolistbeep

# Match without pattern
# ex. > rm *~398
# remove * without a file "398". For test, use "echo *~398"
setopt extended_glob

# Keybind configuration
bindkey -e

# Backspace key
bindkey "^?" backward-delete-char

# historical backward/forward search with linehead string binded to ^P/^N
autoload history-search-end
zle -N history-beginning-search-backward-end history-search-end
zle -N history-beginning-search-forward-end history-search-end
bindkey "^p" history-beginning-search-backward-end
bindkey "^n" history-beginning-search-forward-end
bindkey "\\ep" history-beginning-search-backward-end
bindkey "\\en" history-beginning-search-forward-end

# Command history configuration
HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000

# 登録済コマンド行は古い方を削除
setopt hist_ignore_all_dups

# historyの共有
setopt share_history

# 余分な空白は詰める
setopt hist_reduce_blanks

# add history when command executed.
setopt inc_append_history

# history (fc -l) コマンドをヒストリリストから取り除く。
setopt hist_no_store

# サスペンド中のプロセスと同じコマンド名を実行した場合はリジュームする
setopt auto_resume

# コマンド名に / が含まれているとき PATH 中のサブディレクトリを探す
setopt path_dirs

# ^でcd ..する
function cdup() {
  echo
  cd ..
  zle reset-prompt
}
zle -N cdup
bindkey '^^' cdup

# URLをコピペしたときに自動でエスケープ
autoload -Uz url-quote-magic
zle -N self-insert url-quote-magic

# Completion configuration
fpath=(~/.zsh/functions/Completion ${fpath})
autoload -U compinit
compinit -u

# zsh editor
autoload zed

# Prediction configuration
autoload predict-on
#predict-off

# Command Line Stack [Esc]-[q]
bindkey -a 'q' push-line

# Alias configuration
#
# expand aliases before completing
#
setopt complete_aliases     # aliased ls needs if file/dir completions work
alias where="command -v"
