" Vimっす。vi互換なしっす。
set nocompatible
" キーマップリーダー
let mapleader = ","
" スクロール時の余白確保
set scrolloff=5
" 一行に長い文章を書いていても自動折り返しをしない
set textwidth=0
" バックアップ取らない
set nobackup
" 他で書き換えられたら自動で読み直す
set autoread
" スワップファイル作らない
set noswapfile
" 編集中でも他のファイルを開けるようにする
set hidden
" バックスペースでなんでも消せるように
set backspace=indent,eol,start
" テキスト整形オプション，マルチバイト系を追加
set formatoptions=lmoq
" ビープをならさない
set vb t_vb=
" Exploreの初期ディレクトリ
set browsedir=buffer
" カーソルを行頭、行末で止まらないようにする
set whichwrap=b,s,h,l,<,>,[,]
" コマンドをステータス行に表示
set showcmd
" 現在のモードを表示
set showmode
" モードラインは無効
set modelines=0
" tabを使わない
set expandtab
" インデントを賢く
set smartindent
" tab幅を半角2文字に
set ts=2 sw=2 sts=2
" search
set nohlsearch
set ignorecase
set smartcase
set incsearch
" statusline
set laststatus=2
set statusline=%<%f\ %m%r%h%w%{'['.(&fenc!=''?&fenc:&enc).':'.&ff.']'}%=%l,%c%v%8p
" encoding
set enc=utf8
" backup
set nobackup
" color scheme
colorscheme wombat256mod

" OSのクリップボードを使用する
set clipboard+=unnamed
"ヤンクした文字は、システムのクリップボードに入れる"
set clipboard=unnamed
" 挿入モードでCtrl+kを押すとクリップボードの内容を貼り付けられるようにする "
imap <C-K>  <ESC>"*pa

" Ev/Rvでvimrcの編集と反映
command! Ev edit $MYVIMRC
command! Rv source $MYVIMRC


"Escの2回押しでハイライト消去
nmap <ESC><ESC> ;nohlsearch<CR><ESC>

" 保存時に行末の空白を除去する
autocmd BufWritePre * :%s/\s\+$//ge
" 保存時にtabをスペースに変換する
autocmd BufWritePre * :%s/\t/  /ge

" Ctrl-iでヘルプ
nnoremap <C-h>  :<C-u>help<Space>
" カーソル下のキーワードをヘルプでひく
nnoremap <C-h><C-h> :<C-u>help<Space><C-r><C-w><Enter>

" カーソル行をハイライト
set cursorline
" カレントウィンドウにのみ罫線を引く
augroup cch
  autocmd! cch
  autocmd WinLeave * set nocursorline
  autocmd WinEnter,BufRead * set cursorline
augroup END
:hi clear CursorLine
:hi CursorLine gui=underline
highlight CursorLine ctermbg=black guibg=black

"------------------------------------
" vundle.git
"------------------------------------
set nocompatible
filetype off
set rtp+=~/.vim/vundle.git/
call vundle#rc()
" My Bundles here:
Bundle 'surround.vim'
Bundle 'YankRing.vim'
Bundle 'wombat256.vim'
Bundle 'The-NERD-Commenter'
Bundle 'snipMate'
Bundle 'vim-ruby'
Bundle 'rails.vim'



" from github:
Bundle 'git://github.com/motemen/git-vim.git'
Bundle 'git://github.com/Shougo/neocomplcache.git'
Bundle 'git://github.com/Shougo/unite.vim.git'
Bundle 'git://github.com/tsukkee/unite-help.git'
filetype plugin indent on

"------------------------------------
" surround.vim
"------------------------------------
" s, ssで選択範囲を指定文字でくくる
nmap s <Plug>Ysurround
nmap ss <Plug>Yssurround
