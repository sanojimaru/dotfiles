;; Japanese
(set-language-environment 'Japanese)
(set-default-coding-systems 'utf-8-unix)
(set-terminal-coding-system 'utf-8-unix)
(set-keyboard-coding-system 'sjis-mac)
(set-clipboard-coding-system 'sjis-mac)
(setq-default buffer-file-coding-system 'utf-8)
(prefer-coding-system 'utf-8)

;; Kill wellcome screen
(setq inhibit-splash-screen t)

;; Disable auto save
(setq make-backup-files nil)
(setq auto-save-default nil)

;; Show line and column number
(column-number-mode t)
(line-number-mode t)

;; Show parenthesis
(show-paren-mode t)

;; Hilight cursor line
(defface hlline-face
  '((((class color) (background dark)) (:background "dark slate gray"))
    (((class color) (background light)) (:background "ForestGreen"))
    (t ()))
  "*Face used by hl-line.")
(setq hl-line-face 'hlline-face)
(global-hl-line-mode)

;; Don't use tab
(setq-default tab-width 4 indent-tabs-mode nil)

;; Show trailing whitespace
(when (boundp 'show-trailing-whitespace)
  (setq-default show-trailing-whitespace t))

;; Show Special chars
(defface my-face-b-1 '((t (:background "medium aquamarine"))) nil)
(defface my-face-b-1 '((t (:background "dark turquoise"))) nil)
(defface my-face-b-2 '((t (:background "cyan"))) nil)
(defface my-face-b-2 '((t (:background "SeaGreen"))) nil)
(defface my-face-u-1 '((t (:foreground "SteelBlue" :underline t))) nil)
(defvar my-face-b-1 'my-face-b-1)
(defvar my-face-b-2 'my-face-b-2)
(defvar my-face-u-1 'my-face-u-1)
(defadvice font-lock-mode (before my-font-lock-mode ())
  (font-lock-add-keywords
   major-mode
   '(
     ("　" 0 my-face-b-1 append)
     ("\t" 0 my-face-b-2 append)
     ("[ ]+$" 0 my-face-u-1 append)
     )))
(ad-enable-advice 'font-lock-mode 'before 'my-font-lock-mode)
(ad-activate 'font-lock-mode)
(add-hook 'find-file-hooks '(lambda ()
                              (if font-lock-mode
                                  nil
                                (font-lock-mode t))))

;; auto complete parenthesis
(global-set-key (kbd "(") 'skeleton-pair-insert-maybe)
(global-set-key (kbd "{") 'skeleton-pair-insert-maybe)
(global-set-key (kbd "[") 'skeleton-pair-insert-maybe)
(global-set-key (kbd "\"") 'skeleton-pair-insert-maybe)
(global-set-key (kbd "'") 'skeleton-pair-insert-maybe)
(setq skeleton-pair t)

;; for Cocoa
(when (eq window-system 'ns)
  ;; enable anti-alias
  (setq mac-allow-anti-aliasing t)
  ;; control, option
  (setq mac-control-modifier 'control)
  (setq mac-option-modifier 'meta)
  ;; Key-bindings
  (define-key global-map [s-return] 'ns-toggle-fullscreen))

;; for window system
(if window-system
    (progn
      (set-frame-parameter nil 'alpha 95)))

;; window move
(windmove-default-keybindings)

;; Fonts
(let* ((size 13)
       (asciifont "Ricty")
       (jpfont "Ricty")
       (h (* size 10))
       (fontspec (font-spec :family asciifont))
       (jp-fontspec (font-spec :family jpfont)))
  (set-face-attribute 'default nil :family asciifont :height h)
  (set-fontset-font nil 'japanese-jisx0213.2004-1 jp-fontspec)
  (set-fontset-font nil 'japanese-jisx0213-2 jp-fontspec)
  (set-fontset-font nil 'katakana-jisx0201 jp-fontspec)
  (set-fontset-font nil '(#x0080 . #x024F) fontspec)
  (set-fontset-font nil '(#x0370 . #x03FF) fontspec))

;; load-path
(let ((default-directory (expand-file-name "~/.emacs.d/elisp")))
  (add-to-list 'load-path default-directory)
  (if (fboundp 'normal-top-level-add-subdirs-to-load-path)
      (normal-top-level-add-subdirs-to-load-path)))

;; color-theme.el
(when (require 'color-theme)
  (color-theme-initialize)
  ;; color-theme-solorized.el
  (when (require 'color-theme-solarized)
    (color-theme-solarized-dark)))

;; install-elisp.el
(when (require 'install-elisp nil t)
  (setq install-elisp-repository-directory "~/.emacs.d/elisp"))

;; auto-install.el
(when (require 'auto-install nil t)
  (setq auto-install-directory "~/.emacs.d/elisp/auto-install")
  (auto-install-update-emacswiki-package-name t)
  (auto-install-compatibility-setup))

;; anything
(require 'anything-startup)
(defvar anything-prefix-map)
(define-prefix-command 'anything-prefix-map)
(define-key global-map (kbd "C-;") 'anything-prefix-map)
(define-key anything-prefix-map (kbd "C-;") 'anything-for-files)
(define-key anything-prefix-map (kbd "C-f") 'anything-find-files)
(define-key anything-prefix-map (kbd "C-b") 'anything-for-buffers)
(define-key anything-prefix-map (kbd "C-r") 'anything-recentf)
(define-key anything-prefix-map (kbd "C-h") 'anything-help)

;; auto-save-buffers-enhanced.el
(require 'auto-save-buffers-enhanced)
(auto-save-buffers-enhanced t)

;; emacsclient
(server-start)