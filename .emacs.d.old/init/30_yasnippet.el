;; yasnippet
;; http://code.google.com/p/yasnippet/
(when (require 'yasnippet nil t)
  (yas/initialize)
  (yas/load-directory "~/.emacs.d/elisp/yasnippet-0.6.1c/snippets"))