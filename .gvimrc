" size
set co=190
set lines=60
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
" transparent
set transparency=10
" color
set t_Co=256
set background=dark
colorscheme solarized
" font
set gfn=Ricty\ Regular:h13.5
set gfw=Ricty\ Regular:h13.5
" fullscreen
set fuoptions=maxvert,maxhorz
au GUIEnter * set fullscreen
