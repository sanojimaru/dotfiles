;; php-mode
;; http://sourceforge.net/projects/php-mode/files/php-mode/1.5.0/
;; (autoload 'php-mode "php-mode" "PHP editing mode" t)
(require 'php-mode)
(add-to-list 'auto-mode-alist '("\\.php$" . php-mode))

(add-hook 'php-mode-hook
          '(lambda ()
             (setq php-indent-level 4)
             (setq php-mode-force-pear t)
             (setq tab-width 4)
             (setq php-manual-path "/usr/share/doc/php/html")
             (setq php-search-url  "http://www.phppro.jp/")
             (setq php-manual-url  "http://www.phppro.jp/phpmanual")))

;; ctp-mode
(require 'nxml-mode)
(add-to-list 'auto-mode-alist '("\\.ctp$" . nxml-mode))
(mmm-add-mode-ext-class 'nxml-mode "\\.ctp$" 'mmm-js)
(mmm-add-mode-ext-class 'nxml-mode "\\.ctp$" 'mmm-css)

;; php-eval
;; (install-elisp "http://www.ne.jp/asahi/alpha/kazu/pub/emacs/php-eval.el")
(require 'php-eval)
; リージョン内のコード(<?php ?>がなくてもOK)を評価
; http://d.hatena.ne.jp/kitokitoki/20100605/p1
(defun my-php-eval-region ()
  (interactive)
  (when (region-active-p)
    (let ((region-str (buffer-substring-no-properties (region-beginning) (region-end)))
          (result-buf "*php*")
          (temp-file "/tmp/tmp.php"))
      (with-temp-file temp-file
        (insert "<?php \n" region-str))
      (shell-command (concat "php " temp-file) result-buf)
      (view-buffer-other-window result-buf t
                                (lambda (buf)
                                  (kill-buffer-and-window)
                                  (delete-file temp-file))))))
(eval-after-load 'php-eval
  '(progn
    (define-key php-mode-map (kbd "C-c C-r C-r") 'my-php-eval-region)
    (define-key php-mode-map (kbd "C-c C-r C-v") 'php-eval-display-buffer)))