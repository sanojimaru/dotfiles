;; auto-complete
;; (auto-install-batch "auto-complete development version")
(when (require 'auto-complete-config nil t)
  (add-to-list 'ac-dictionary-directories "~/.emacs.d/ac-dict")
  (define-key ac-mode-map (kbd "M-TAB") 'auto-complete)
  (ac-config-default)
  (ac-set-trigger-key "TAB")
  (setq ac-delay 0.1))