# Environment variable configuration
export LANG=en_US.UTF-8
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# OSにより端末を判定
alias ls="ls -lG -w"
alias ks="ls"
alias sl="ls"

# rbenv
export PATH="$HOME/.rbenv/bin:$PATH"
eval "$(rbenv init -)"
export RBENV_VERSION=1.9.3-p0

# node nvm
source $HOME/.nvm/nvm.sh

# cakephp
alias cake='$HOME/workspace/src/cakephp/lib/Cake/Console/cake "$@"'
alias cake13='$HOME/workspace/src/cakephp1.3/cake/console/cake "$@"'

# python
alias wget-bootstrap.py='wget "http://svn.zope.org/*checkout*/zc.buildout/trunk/bootstrap/bootstrap.py"'
[[ -s $HOME/.pythonbrew/etc/bashrc ]] && source $HOME/.pythonbrew/etc/bashrc

# android
export ANDROID_SDK=$HOME/workspace/android-sdk
export PATH=$PATH:$ANDROID_SDK/platform-tools:$ANDROID_SDK/tools

# Titanium
export TITANIUM_SDK='/Library/Application\ Support/Titanium/mobilesdk/osx/1.7.5'
alias titanium=$TITANIUM_SDK/titanium.py

# vim
export EDITOR=/Applications/MacVim.app/Contents/MacOS/Vim
alias vim='/Applications/MacVim.app/Contents/MacOS/Vim "$@"'
alias vi='vim'
alias v='vim'

# emacs
alias emacs='/Applications/Emacs.app/Contents/MacOS/Emacs "$@"'
alias em='emacs'
alias e='emacs'

# MySQL
alias mysql='mysql -uroot -hworkspace.dev "$@"'

# PEAR
export PATH=$HOME/.pear/bin:$PATH

# git-flow-completion
source ~/workspace/src/git-flow-completion/git-flow-completion.zsh

# AWS
export JAVA_HOME="$(/usr/libexec/java_home)"
export EC2_HOME="/usr/local/Cellar/ec2-api-tools/1.5.2.3/jars"
export EC2_PRIVATE_KEY="$(/bin/ls $HOME/files/secrets/aws_security_certificates/eds_pk-*.pem)"
export EC2_CERT="$(/bin/ls $HOME/files/secrets/aws_security_certificates/eds_cert-*.pem)"
export EC2_REGION=ap-northeast-1
export AWS_RDS_HOME="/usr/local/Cellar/rds-command-line-tools/1.3.003/jars"
