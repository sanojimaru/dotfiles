# Environment variable configuration
export LANG=en_US.UTF-8
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8

alias ls="ls -lG -w"
alias ks="ls"
alias sl="ls"

# homebrew
export LDFLAGS="-L/usr/local/opt/libtool/lib"
export CPPFLAGS="-I/usr/local/opt/libtool/include"
export PATH="/usr/local/sbin:$PATH"

# Play
export PATH="$HOME/src/play-2.1.0:$PATH"

# php-fpm
export PATH="$(brew --prefix josegonzalez/php/php54)/bin:$PATH"

# nave
alias nave='$HOME/src/nave/nave.sh "$@"'
export PATH="/Users/sanojimaru/node_modules/.bin:$PATH"

# rbenv
export PATH="$HOME/bin:$HOME/.rbenv/bin:$PATH"
eval "$(rbenv init - zsh)"
source ~/.rbenv/completions/rbenv.zsh

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

# Sublime text 2
alias subl='/Applications/Sublime\ Text\ 2.app/Contents/SharedSupport/bin/subl "$@"'
alias e='subl'

# vim
export EDITOR=/Applications/MacVim.app/Contents/MacOS/Vim
alias vim='/Applications/MacVim.app/Contents/MacOS/Vim "$@"'
alias vi='vim'
alias v='vim'

# MySQL
alias mysql='mysql -uroot -hworkspace.dev "$@"'
alias mysqldump='mysqldump -uroot -hworkspace.dev "$@"'
alias mysqllocal='mysql -hlocalhost "$@"'
alias mysqldumplocal='mysqldump -hlocalhost "$@"'

# git-flow-completion
source ~/src/git-flow-completion/git-flow-completion.zsh

# AWS
export JAVA_HOME="$(/usr/libexec/java_home)"
export EC2_HOME="/usr/local/Cellar/ec2-api-tools/1.5.2.3/jars"
export EC2_PRIVATE_KEY="$(/bin/ls $HOME/iccom_ssh_keys/aws_security_certificates/eds_pk-*.pem)"
export EC2_CERT="$(/bin/ls $HOME/iccom_ssh_keys/aws_security_certificates/eds_cert-*.pem)"
export EC2_REGION=ap-northeast-1
export AWS_RDS_HOME="/usr/local/Cellar/rds-command-line-tools/1.3.003/jars"

# picmix接続
alias sshpf_picmix=`cat <<EOF
sudo ssh -C -N -f -L 80:wwwd.picmix.jp:80 dev.ic-com.co.jp &&
ssh -C -N -f -L 80:wwwt.picmix.jp:80 dev.ic-com.co.jp
EOF`

# 窓タッチ
alias sshpf_madotouch='ssh -C -N -f -L 13389:10.0.1.246:3389 madotouch.gateway'
