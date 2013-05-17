# Environment variable configuration
export LANG=ja_JP.UTF-8
export LANGUAGE=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8

alias ls="ls -lG -w"
alias ks="ls"
alias sl="ls"

export PATH="$(brew --prefix)/bin:$(brew --prefix)/sbin:~/bin:$PATH"

# Sublime text 2
#alias subl='/Applications/Sublime\ Text\ 2.app/Contents/SharedSupport/bin/subl "$@"'
#alias e='subl'

# vim
export EDITOR=/Applications/MacVim.app/Contents/MacOS/Vim
alias vim='/Applications/MacVim.app/Contents/MacOS/Vim "$@"'
alias vi='vim'
alias v='vim'

# git-flow-completion
source /usr/local/share/zsh/site-functions/git-flow-completion.zsh
 
