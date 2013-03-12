" jslint.vim
autocmd BufLeave     <buffer> call jslint#clear()
autocmd BufWritePost <buffer> call jslint#check()
autocmd CursorMoved  <buffer> call jslint#message()
