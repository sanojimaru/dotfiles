;; Warning
(defvar org-directory "")

;; anything
;; (auto-install-batch "anything")
(require 'anything-startup)

;; anything-etags
;; (auto-install-from-emacswiki "anything-etags.el")
;; (require 'anything-etags)

;; anything-gtags
;; (auto-install-from-emacswiki "anything-gtags.el")
(require 'anything-gtags)
(define-key global-map (kbd "C-x t")
  (lambda ()
    "Tag jump using etags, gtags and anything."
    (interactive)
    (let* ((initial-pattern (regexp-quote (or (thing-at-point 'symbol) ""))))
      (anything (list anything-c-source-gtags-select
                      anything-c-source-etags-select))
      "Find Tag: " nil)))

;; anything
(define-key global-map (kbd "M-l") 'anything)