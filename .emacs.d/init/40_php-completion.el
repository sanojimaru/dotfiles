;; php-completion
;; (auto-install-batch "php-completion")
(defun php-completion()
  (require 'php-completion)
  (php-completion-mode t)
  (define-key php-mode-map (kbd "C-o") 'phpcmp-complete)
  (when (require 'auto-complete nil t)
    (make-variable-buffer-local 'ac-sources)
    (add-to-list 'ac-sources 'ac-source-php-completion)
    (auto-complete-mode t)))

(add-hook 'php-mode-hook 'php-completion)