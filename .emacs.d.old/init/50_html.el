;; html-mode
(autoload 'nxml-mode "nxml-mode")
(add-to-list 'auto-mode-alist '("\\.html$" . nxml-mode))
(mmm-add-mode-ext-class 'nxml-mode "\\.html$" 'mmm-js)
(mmm-add-mode-ext-class 'nxml-mode "\\.html$" 'mmm-css)

;; css-mode
(autoload 'css-mode "css-mode")
(add-to-list 'auto-mode-alist '("\\.css$" . css-mode))

