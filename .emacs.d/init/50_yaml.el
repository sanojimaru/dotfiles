;; yaml-mode
;; (install-elisp "https://github.com/yoshiki/yaml-mode/raw/master/yaml-mode.el")
(require 'yaml-mode)
(add-to-list 'auto-mode-alist '("\\.yml$" . yaml-mode))
(add-hook 'yaml-mode-hook
          '(lambda ()
             (define-key yaml-mode-map (kbd "C-m") 'newline-and-indent)))