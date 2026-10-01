alias ls="ls -la"
alias vi="vim"

setopt auto_cd pushd_ignore_dups no_clobber hist_reduce_blanks nonomatch

# 補完と autosuggestions (brew)
FPATH="$HOMEBREW_PREFIX/share/zsh-completions:$FPATH"
autoload -Uz compinit && compinit
. "$HOMEBREW_PREFIX/share/zsh-autosuggestions/zsh-autosuggestions.zsh"

command -v direnv >/dev/null && eval "$(direnv hook zsh)"
[ -f "$HOMEBREW_PREFIX/share/google-cloud-sdk/completion.zsh.inc" ] && . "$HOMEBREW_PREFIX/share/google-cloud-sdk/completion.zsh.inc"
