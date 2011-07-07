;; redo+
;; (install-elisp "http://www.emacswiki.org/emacs/download/redo+.el")
(require 'redo+)
(define-key global-map (kbd "C-^") 'redo)

;; undohist
;; (install-elisp "http://cx4a.org/pub/undohist.el")
;; (require 'undohist)
;; (undohist-initialize)

;; wdired
(require 'wdired)
(define-key dired-mode-map "r" 'wdired-change-to-wdired-mode)