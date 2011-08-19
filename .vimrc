set nocompatible
" キーマップリーダー
let mapleader = "\\"
" スクロール時の余白確保
set scrolloff=5
" 一行に長い文章を書いていても自動折り返しをしない
set textwidth=0
" バックアップ取らない
set nobackup
" スワップファイル作らない
set noswapfile
" 他で書き換えられたら自動で読み直す
set autoread
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
" 自動でインデント
set autoindent
" tab幅を半角2文字に
set tabstop=2
set shiftwidth=2
set softtabstop=2
" tabを賢く
set smarttab
" 行番号表示
set number
"モード表示
set showmode
"編集中のファイル名を表示
set title
"ルーラーの表示
set ruler
"入力中のコマンドをステータスに表示する
set showcmd
"括弧入力時の対応する括弧を表示
set showmatch
" カラー表示
syntax on
" search
set nohlsearch
set ignorecase
set smartcase
set incsearch
" statusline
set laststatus=2
set statusline=%<%f\ %y\ %m%r%h%w%{'['.(&fenc!=''?&fenc:&enc).':'.&ff.']'}%=%l,%c%8p
" encoding
set enc=utf8
" backup
set nobackup
" color
set t_Co=256
colorscheme wombat256mod
" font
set gfn=Ricty\ Regular:h12
set gfw=Ricty\ Regular:h12
" 特殊文字見せる
set list
set listchars=tab:>.,trail:_,nbsp:%,extends:>,precedes:<

" Enable mouse support.
set mouse=a
" For screen.
if &term =~ "^screen"
  augroup MyAutoCmd
    autocmd VimLeave * :set mouse=
  augroup END
  " screenでマウスを使用するとフリーズするのでその対策
  set ttymouse=xterm2
endif

" GVim setting
if has("gui_running")
  " size
  set co=160
  set lines=50
  " hide menubar, toolbar, scrollbar
  set guioptions-=m
  set guioptions-=T
  set guioptions-=r
  set guioptions-=L
  " Show popup menu if right click.
  set mousemodel=popup
  " Don't focus the window when the mouse pointer is moved.
  set nomousefocus
  " Hide mouse pointer on insert mode.
  set mousehide
endif

" OSのクリップボードを使用する
set clipboard+=unnamed
"ヤンクした文字は、システムのクリップボードに入れる
set clipboard=unnamed

" Ev/Rvでvimrcの編集と反映
command! Ev edit $HOME/.vimrc
command! Rv source $HOME/.vimrc

" 保存時に行末の空白を除去する
autocmd BufWritePre * :%s/\s\+$//ge
" 保存時にtabをスペースに変換する
autocmd BufWritePre * :%s/\t/  /ge

" 矩形選択で自由に移動する
set virtualedit+=block

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
" keymap
"------------------------------------
" C-a, Tab, C-eで行頭、先頭、行末移動
nnoremap <C-e> <S-a>
nnoremap <C-a> 0i
nnoremap <Tab> ^i

" 挿入モードでCtrl+kを押すとクリップボードの内容を貼り付けられるようにする "
imap <C-K>  <ESC>"*pa

"Escの2回押しでハイライト消去
nmap <ESC><ESC> :nohlsearch<CR><ESC>

" Ctrl-iでヘルプ
nnoremap <C-h>  :<C-u>help<Space>
" カーソル下のキーワードをヘルプでひく
nnoremap <C-h><C-h> :<C-u>help<Space><C-r><C-w><Enter>

" F2で前のバッファ
map <F2> <ESC>:bp<CR>
" F3で次のバッファ
map <F3> <ESC>:bn<CR>
" F4でバッファを削除する
map <F4> <ESC>:bw<CR>

" 最後に編集された位置に移動
nnoremap gb '[
nnoremap gp ']

" 対応する括弧に移動
nnoremap [ %
nnoremap ] %

"ビジュアルモード時vで行末まで選択
vnoremap v $h

" 括弧を自動補完
inoremap { {}<LEFT>
inoremap [ []<LEFT>
inoremap ( ()<LEFT>
inoremap " ""<LEFT>
inoremap ' ''<LEFT>

" ウィンドウ移動
nnoremap <C-Right> ;<C-l>j
nnoremap <C-j> ;<C-w>j
nnoremap <C-k> ;<C-k>j
nnoremap <C-l> ;<C-l>j
nnoremap <C-h> ;<C-h>j


"------------------------------------
" vundle.git
"------------------------------------
set nocompatible
filetype off
set rtp+=~/.vim/vundle.git/
call vundle#rc()

" My Bundles here:
" from github:
Bundle 'git://github.com/vim-scripts/wombat256.vim.git'
Bundle 'git://github.com/tpope/vim-surround.git'
Bundle 'git://github.com/chrismetcalf/vim-yankring.git'
Bundle 'git://github.com/scrooloose/nerdcommenter.git'
Bundle 'git://github.com/msanders/snipmate.vim.git'
Bundle 'git://github.com/tpope/vim-rails.git'
Bundle 'git://github.com/vim-ruby/vim-ruby.git'
Bundle 'git://github.com/Shougo/neocomplcache.git'
Bundle 'git://github.com/Shougo/unite.vim.git'
Bundle 'git://github.com/tsukkee/unite-help.git'
Bundle 'git://github.com/tpope/vim-haml.git'
Bundle 'git://github.com/othree/html5.vim.git'
Bundle 'git://github.com/hail2u/vim-css3-syntax.git'
Bundle 'git://github.com/othree/javascript-syntax.vim.git'
Bundle 'git://github.com/vim-scripts/Javascript-Indentation.git'
Bundle 'git://github.com/kchmck/vim-coffee-script.git'
Bundle 'git://github.com/cakebaker/scss-syntax.vim.git'
Bundle 'git://github.com/Shougo/vimproc.git'
Bundle 'git://github.com/Shougo/vimshell.git'
Bundle 'git://github.com/thinca/vim-quickrun.git'
Bundle 'smoothPageScroll.vim'

filetype on
filetype plugin on
filetype indent on

"------------------------------------
" filetype
"------------------------------------
" .phpにhtmlモードを追加する
autocmd BufNewFile,BufRead *.ctp set filetype=php.html
autocmd BufNewFile,BufRead *.php set filetype=php.html

" .jstにerbモード、htmlモードを追加する
autocmd BufNewFile,BufRead *.jst set filetype=eruby.html

" .erbにいろいろモードを追加する
autocmd BufNewFile,BufRead *.erb set filetype=eruby.html
autocmd BufNewFile,BufRead *.css.erb set filetype=eruby.css
autocmd BufNewFile,BufRead *.scss.erb set filetype=eruby.css
autocmd BufNewFile,BufRead *.js.erb set filetype=eruby.js
autocmd BufNewFile,BufRead *.coffee.erb set filetype=eruby.coffee

"------------------------------------
" SmoothPageScroll
"------------------------------------
let g:smooth_page_scroll_delay = 0
map <PageDown> :call SmoothPageScrollDown()<CR>
map <PageUp> :call SmoothPageScrollUp()<CR>
map <C-f> :call SmoothPageScrollDown()<CR>
map <C-b> :call SmoothPageScrollUp()<CR>


"------------------------------------
" vim-quickrun
"------------------------------------
let g:quickrun_config = {}
let g:quickrun_config['ruby.rspec'] = { 'command': 'rspec' }

" ruby.spec
augroup RSpec
  autocmd!
  autocmd BufWinEnter, BufNewFile *_spec.rb set filetype=ruby.rspec
augroup END

"------------------------------------
" VimShell
"------------------------------------
let g:vimshell_enable_interactive = 1
let g:vimshell_enable_auto_slash = 1

"------------------------------------
" SnipMate
"------------------------------------
let g:snippets_dir = $HOME.'/.vim/snippets'

"------------------------------------
" neocomplcache
"------------------------------------
" 起動時に有効化
let g:neocomplcache_enable_at_startup = 1
" 大文字小文字を区別する
let g:neocomplcache_enable_smart_case = 1
" キャメルケース補完を有効にする
let g:neocomplcache_enable_camel_case_completion = 1
" アンダーバー補完を有効にする
let g:neocomplcache_enable_underbar_completion = 1
" シンタックスファイルの補完対象キーワードとする最小の長さ
let g:neocomplcache_min_syntax_length = 3
let g:neocomplcache_min_keyword_length = 3
let g:neocomplcache_plugin_completion_length = {
  \ 'snipmate_complete' : 1,
  \ 'keyword_complete' : 2,
  \ 'syntax_complete' : 2
  \ }

" 候補popup時に先頭の候補を選択しておく
let g:neocomplcache_enable_auto_select = 1

" Define snippets directory.
"let g:neocomplcache_snippets_dir = $HOME.'/.vim/snippets'

" Define dictionary.
let g:neocomplcache_dictionary_filetype_lists = {
    \ 'default' : '',
    \ 'java' : '~/.vim/dict/java.dict',
    \ 'javascript' : '~/.vim/dict/javascript.dict',
    \ 'php' : '~/.vim/dict/php.dict',
    \ 'vim' : '~/.vim/dict/vim.dict'}

" Define keyword.
if !exists('g:neocomplcache_keyword_patterns')
  let g:neocomplcache_keyword_patterns = {}
endif
let g:neocomplcache_keyword_patterns['default'] = '\h\w*'

" Recommended key-mappings.
" <CR>: close popup and save indent.
"inoremap <expr><CR>  neocomplcache#smart_close_popup()."\<CR>"
" <TAB>: completion.
inoremap <expr><TAB>  pumvisible() ? "\<C-n>" : "\<TAB>"
" <C-h>, <BS>: close popup and delete backword char.
inoremap <expr><C-h> neocomplcache#smart_close_popup()."\<C-h>"
inoremap <expr><BS> neocomplcache#smart_close_popup()."\<C-h>"
inoremap <expr><C-y>  neocomplcache#close_popup()
inoremap <expr><C-e>  neocomplcache#cancel_popup()

" Enable omni completion.
autocmd FileType css setlocal omnifunc=csscomplete#CompleteCSS
autocmd FileType html,markdown setlocal omnifunc=htmlcomplete#CompleteTags
autocmd FileType xml setlocal omnifunc=xmlcomplete#CompleteTags
autocmd FileType javascript setlocal omnifunc=javascriptcomplete#CompleteJS
autocmd FileType python setlocal omnifunc=pythoncomplete#Complete
autocmd FileType ruby setlocal omnifunc=rubycomplete#Complete

" Enable heavy omni completion.
"if !exists('g:neocomplcache_omni_patterns')
"  let g:neocomplcache_omni_patterns = {}
"endif
"let g:neocomplcache_omni_patterns.ruby = '[^. *\t]\.\w*\|\h\w*::'
"let g:neocomplcache_omni_patterns.php = '[^. \t]->\h\w*\|\h\w*::'


"------------------------------------
" surround.vim
"------------------------------------
" s, ssで選択範囲を指定文字でくくる
nmap s <Plug>Ysurround
nmap ss <Plug>Yssurround

"------------------------------------
" unite.vim
"------------------------------------
" 入力モードで開始する
let g:unite_enable_start_insert=1
" バッファ一覧
noremap <C-x><C-l> :Unite buffer<CR>
" ファイル一覧
noremap <C-x><C-o> :Unite -buffer-name=file file<CR>
" 最近使ったファイルの一覧
noremap <C-x><C-r> :Unite file_mru<CR>
" ESCキーを2回押すと終了する
au FileType unite nnoremap <silent> <buffer> <ESC><ESC> :q<CR>
au FileType unite inoremap <silent> <buffer> <ESC><ESC> <ESC>:q<CR>

"------------------------------------
" rails.vim
"------------------------------------
let g:rails_level=4
let g:rails_default_database='mysql'
