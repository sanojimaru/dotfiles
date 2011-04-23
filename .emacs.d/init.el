;; init.el written by Hirohide Sano (sanojimaru@gmail.com)

;; load-path
(defun add-to-load-path(&rest paths)
  (let (path)
    (dolist (path paths paths)
      (let ((default-directory (expand-file-name (concat user-emacs-directory path))))
	(add-to-list 'load-path default-directory)
	(if (fboundp 'normal-top-level-add-subdirs-to-load-path)
	    (normal-top-level-add-subdirs-to-load-path))))))
(add-to-load-path "elisp" "conf" "auto-install")

;; auto-install
;; (install-elisp "http://www.emacswiki.org/emacs/download/auto-install.el")
(require 'auto-install nil t)
(setq auto-install-directory "~/.emacs.d/auto-install")
;; (auto-install-update-emacswiki-package-name t)
(auto-install-compatibility-setup)


;; init-loader
;; (install-elisp "http://coderepos.org/share/export/38873/lang/elisp/init-loader/init-loader.el")
(require 'init-loader)
(init-loader-load "~/.emacs.d/init")

;; 00_* 一般設定
;; 10_* 起動前実行
;; 20_* 関数定義
;; 30_* 追加機能
;; 40_* マイナーモード
;; 50_* メジャーモード
;; 90_* 起動後実行
(custom-set-variables
  ;; custom-set-variables was added by Custom.
  ;; If you edit it by hand, you could mess it up, so be careful.
  ;; Your init file should contain only one such instance.
  ;; If there is more than one, they won't work right.
 '(gud-gdb-command-name "gdb --annotate=1")
 '(large-file-warning-threshold nil)
 '(safe-local-variable-values (quote ((encoding . utf-8) (clmemo-mode . t)))))
(custom-set-faces
  ;; custom-set-faces was added by Custom.
  ;; If you edit it by hand, you could mess it up, so be careful.
  ;; Your init file should contain only one such instance.
  ;; If there is more than one, they won't work right.
 )
