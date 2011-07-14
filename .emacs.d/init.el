;; start server
(server-start)

;; set user infomation
(setq user-full-name "sanojimaru")
(setq user-mail-address "sanojimaru@gmail.com")

; emacs の種類バージョンを判別するための変数を定義
;; @see http://github.com/elim/dotemacs/blob/master/init.el
(defun x->bool (elt) (not (not elt)))
(defvar emacs22-p (equal emacs-major-version 22))
(defvar emacs23-p (equal emacs-major-version 23))
(defvar darwin-p (eq system-type 'darwin))
(defvar ns-p (featurep 'ns))
(defvar carbon-p (and (eq window-system 'mac) emacs22-p))
(defvar mac-p (and (eq window-system 'mac) emacs23-p))
(defvar linux-p (eq system-type 'gnu/linux))
(defvar colinux-p (when linux-p
                    (let ((file "/proc/modules"))
                      (and
                      (file-readable-p file)
                       (x->bool
                        (with-temp-buffer
                          (insert-file-contents file)
                          (goto-char (point-min))
                          (re-search-forward "^cofuse\.+" nil t)))))))
(defvar cygwin-p (eq system-type 'cygwin))
(defvar nt-p (eq system-type 'windows-nt))
(defvar meadow-p (featurep 'meadow))
(defvar windows-p (or cygwin-p nt-p meadow-p))

;; OS毎の設定
(cond (mac-p 
       (lambda ()
         (setq auto-install-wget-command "/usr/local/bin/wget"
               default-input-method "macosx")))
      (linux-p 
       (lambda ()
         (setq auto-install-wget-command "/usr/bin/wget"))))

;; 文字コード
;;(set-language-environment 'japanese)
(prefer-coding-system           'utf-8-unix)
(setq                           default-buffer-file-coding-system 'utf-8)
(set-buffer-file-coding-system  'utf-8)
(set-terminal-coding-system     'utf-8)
(set-keyboard-coding-system     'utf-8)
(set-clipboard-coding-system    'utf-8)

;; enable debug mode
(setq debug-on-error t)

;; hide welcome screen
(setq inhibit-splash-screen t)
(setq inhibit-startup-message t)

;; hide menu bar
(menu-bar-mode 0)

;; show pair parenthesis
(setq show-paren-delay 0)
(show-paren-mode t)

;; do not open some frames
(setq ns-pop-up-frames nil)

;; display line number, column number
;(global-linum-mode)
(line-number-mode t)
(column-number-mode t)
(setq default-fill-column 80)

;; hilight current line
(global-hl-line-mode t)

;; window size
(setq initial-frame-alist
      (append
       '((width . 80)
         (height . 50))
       initial-frame-alist))

;; command-key and option-key
;(setq ns-command-modifier (quote meta))
;(setq ns-alternate-modifier (quote super))
(setq mac-pass-control-to-system nil)
(setq mac-pass-command-to-system nil)
(setq mac-pass-option-to-system nil)

;; バックアップファイルを残さない
(setq make-backup-files nil)

;; 自動保存ファイルを終了時に削除
(setq delete-auto-save-files t)

;; ベルを鳴らさない
(setq ring-bell-function 'ignore)

;; 1行ずつスクロール
(setq scroll-step 1)

;; スクロールバーを表示
(set-scroll-bar-mode 'right)

;; モードラインに時計を表示
(display-time)

;; 折り返さない
(setq truncate-lines t)
(setq truncate-partial-width-windows t)

;; インデント設定
(setq-default indent-tabs-mode nil)
(setq-default c-basic-offset 2)
(setq-default tab-width 2)
(c-set-offset 'case-label '+)

;; タブをスペースに変換
(setq-default indent-tabs-mode nil)

;; narrowingを使う
(put 'narrow-to-region 'disabled nil)

;; yesnoをynに
(defalias 'yes-or-no-p 'y-or-n-p)

;; ダイアログボックスを使わない
(setq use-dialog-box nil)
(defalias 'message-box 'message)

;; タイムローケールを英語に
(setq system-time-locale "c")

;; windowの移動をs-矢印に
(windmove-default-keybindings)

;; 引数を load-path へ追加
;; normal-top-level-add-subdirs-to-load-path はディレクトリ中の中で
;; [a-za-z] で開始する物だけ追加するので、追加したくない物は . や _ を先頭に付与しておけばロードしない
;; dolist は emacs 21 から標準関数なので積極的に利用して良い
(defun add-to-load-path (&rest paths)
  (let (path)
    (dolist (path paths paths)
      (let ((default-directory (expand-file-name (concat user-emacs-directory path))))
        (add-to-list 'load-path default-directory)
        (if (fboundp 'normal-top-level-add-subdirs-to-load-path)
            (normal-top-level-add-subdirs-to-load-path))))))

;; add emacs lisp path
(add-to-load-path "site-lisp" "auto-install")

;; auto-install.el
;; http://www.emacswiki.org/emacs/auto-install.el
(require 'auto-install)
(setq auto-install-directory "~/.emacs.d/auto-install/")
(auto-install-update-emacswiki-package-name t)
(auto-install-compatibility-setup)

;; font
(add-to-list 'default-frame-alist '(font . "ricty-12"))

;; full screen
(global-set-key (kbd "M-RET") 'ns-toggle-fullscreen)

;; wombat
;; (install-elisp "http://www.elektronensturm.de/files/dateien/color-theme-wombat.el")
(require 'color-theme-wombat)
(color-theme-wombat)

;; anything.el
;; (auto-install-batch "anything")
(require 'anything-startup)
(define-key global-map (kbd "C-l") 'anything)
(setq anything-sources
      '(anything-c-source-buffers+
        anything-c-source-files-in-current-dir
        anything-c-source-recentf
        anything-c-source-colors
        anything-c-source-man-pages
        anything-c-source-emacs-commands
        anything-c-source-emacs-functions
        ))

;; auto-complete
;; (auto-install-batch "auto-complete development version")
;;(require 'auto-complete)
;;(global-auto-complete-mode t)

;; yasnippet
(add-to-list 'load-path "~/.emacs.d/packages/yasnippet-0.6.1c")
(require 'yasnippet)
(yas/initialize)
(yas/load-directory "~/.emacs.d/packages/yasnippet-0.6.1c/snippets")

;; nxhtml-mode
(load "~/.emacs.d/packages/nxhtml/autostart.el")
(custom-set-variables
 '(indent-region-mode t)
 '(nxhtml-global-minor-mode t)
 '(nxhtml-global-validation-header-mode t)
 '(nxhtml-skip-welcome t))
(custom-set-faces
 '(mumamo-background-chunk-major ((((class color) (min-colors 8)) (:background "*"))))
 '(mumamo-background-chunk-submode1 ((((class color) (min-colors 8)) (:background "grey10")))))
(add-hook 'nxml-mode-hook
          (lambda ()
            (setq auto-fill-mode -1)
            (setq nxml-slash-auto-complete-flag t)
            (setq nxml-child-indent 2)
            (setq indent-tabs-mode t)
            (setq tab-width 2)
            (define-key nxml-mode-map "\r" 'newline-and-indent)))
(add-to-list 'auto-mode-alist '("\\.ctp\\'" . nxhtml-mumamo-mode))

;; php-mode
;; php-completion
;; (auto-install-batch "php-completion")
;;(autoload 'php-mode "php-mode" "Major mode for editing php code." t)
;;(add-to-list 'auto-mode-alist '("\\.php$" . php-mode))
;;(add-to-list 'auto-mode-alist '("\\.inc$" . php-mode))
(add-hook 'php-mode-hook
         (lambda ()
           ;; php-mode
           (c-set-style "stroustrup")
           (setq tab-width 2
                 c-basic-offset 2
                 c-hanging-comment-ender-p nil
                 indent-tabs-mode nil)
           (setq php-manual-path "/usr/share/doc/php/html")
           (setq php-manual-url "http://www.phppro.jp/phpmanual")
           ;; php-completion
           (require 'php-completion)
           (php-completion-mode t)
           (define-key php-mode-map (kbd "C-o") 'phpcmp-complete)
           (when (require 'auto-complete nil t)
             (make-variable-buffer-local 'ac-sources)
             (add-to-list 'ac-sources 'ac-source-php-completion)
             (auto-complete-mode t))))
