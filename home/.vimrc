" 基本設定
set nocompatible        " 互換モードを無効にする
set encoding=utf-8      " ファイルエンコーディングをUTF-8に設定
set fileencoding=utf-8  " 保存時のエンコーディングをUTF-8に設定
set fileencodings=utf-8,cp932,euc-jp,sjis " 読み込み時のエンコーディング候補
set fileformats=unix,dos,mac " ファイルフォーマットを設定
set ambiwidth=double    " 全角文字の幅を2に設定
set backspace=indent,eol,start " バックスペースキーの挙動を設定
set clipboard=unnamed,unnamedplus " システムクリップボードと共有

" 表示設定
set number              " 行番号を表示
set cursorline          " カーソル行を強調表示
set virtualedit=onemore " カーソルを行末の1文字分超えるように設定
set smartindent         " スマートインデントを有効にする
set visualbell          " ビープ音を視覚ベルに変更
set showmatch           " 対応する括弧を強調表示
set laststatus=2        " ステータスラインを常に表示
set wildmode=list:longest " コマンドライン補完をリスト表示
syntax enable           " シンタックスハイライトを有効にする

" タブ設定
set expandtab           " タブをスペースに変換
set tabstop=4           " タブ幅を4に設定
set shiftwidth=4        " 自動インデントの幅を4に設定

" 検索設定
set ignorecase          " 検索時に大文字小文字を区別しない
set smartcase           " 大文字を含む検索では区別する
set incsearch           " インクリメンタルサーチを有効にする
set wrapscan            " 検索をファイル末尾で折り返す
set hlsearch            " 検索結果を強調表示
nmap <Esc><Esc> :nohlsearch<CR><Esc> " Escキーで検索結果の強調表示を解除

" キーマッピング
inoremap jj <Esc>       " インサートモードでjjを押すとEscにマップ
nnoremap j gj           " jで行が折り返されている場合、物理行に移動
nnoremap k gk           " kで行が折り返されている場合、物理行に移動

" カーソル移動の高速化
nnoremap <C-d> <C-d>zz  " ページダウン後にカーソルを中央に配置
nnoremap <C-u> <C-u>zz  " ページアップ後にカーソルを中央に配置
nnoremap n nzzzv        " 次の検索結果に移動後、カーソルを中央に配置
nnoremap N Nzzzv        " 前の検索結果に移動後、カーソルを中央に配置

" ヤンク・クリップボードの共有
set clipboard+=unnamedplus " システムクリップボードと共有

" プラグイン管理（vim-plugを使用する場合）
call plug#begin()

" ここにプラグインを追加
" ファイルツリー
Plug 'preservim/nerdtree'
" ステータスライン
Plug 'vim-airline/vim-airline'
Plug 'vim-airline/vim-airline-themes'
" Gitサポート
Plug 'tpope/vim-fugitive'

call plug#end()

" NERDTreeの設定
" Ctrl+nでNERDTreeをトグル
map <C-n> :NERDTreeToggle<CR>
" Vim起動時にNERDTreeを開く
"autocmd VimEnter * NERDTree

" Airlineの設定
let g:airline#extensions#tabline#enabled = 1   " タブラインを有効にする
let g:airline#extensions#tabline#formatter = 'default'

" バックアップファイルを作成しない
set nobackup
set noswapfile

" 行末の空白を可視化
set listchars=tab:>-,trail:-,extends:>,precedes:<,nbsp:%
set list

" ビジュアルベルを無効化
set t_vb=
set visualbell t_vb=

" マウス操作を有効化
set mouse=a

" 80文字目にラインを表示
set colorcolumn=80

" ファイルタイプごとのインデント設定
augroup fileTypeIndent
    autocmd!
    autocmd BufNewFile,BufRead *.py setlocal tabstop=4 softtabstop=4 shiftwidth=4
    autocmd BufNewFile,BufRead *.rb setlocal tabstop=2 softtabstop=2 shiftwidth=2
    autocmd BufNewFile,BufRead *.js,*.html,*.css setlocal tabstop=2 softtabstop=2 shiftwidth=2
augroup END

" 括弧の自動補完
inoremap ( ()<Left>
inoremap { {}<Left>
inoremap [ []<Left>
inoremap " ""<Left>
inoremap ' ''<Left>


