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
  '((((class color) (background dark)) (:background "#073642"))
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
      ;; Transparancy
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
(require 'color-theme)
(color-theme-initialize)
;; color-theme-solorized.el
(require 'color-theme-solarized)
(color-theme-solarized-dark)

;; Colors
(set-cursor-color "#475c56")
(setq default-frame-alist
      (append
       (list
        '(cursor-color . "#475c56"))
       default-frame-alist))

;; install-elisp.el
(require 'install-elisp)
(setq install-elisp-repository-directory "~/.emacs.d/elisp")
;; auto-install.el
(require 'auto-install nil t)
(setq auto-install-directory "~/.emacs.d/elisp/auto-install")
(auto-install-update-emacswiki-package-name t)
(auto-install-compatibility-setup)

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

;; yasnippet
(when (require 'yasnippet nil t)
  (setq yas/snippet-dirs '("~/.emacs.d/elisp/yasnippet/snippets"
                           "~/.emacs.d/elisp/yasnippet/extras/imported"))
  (yas/global-mode 1)
  (setq yas/trigger-key "TAB")
  (setq yas/next-field-key "TAB")
  (setq yas/prev-field-key "<S-tab>")
  (define-key yas/minor-mode-map (kbd "C-x i i") 'yas/insert-snippet)
  (define-key yas/minor-mode-map (kbd "C-x i f") 'yas/find-snippets)
  (define-key yas/minor-mode-map (kbd "C-x i n") 'yas/new-snippet)
  (define-key yas/minor-mode-map (kbd "C-x i v") 'yas/visit-snippet-file)
  (define-key yas/minor-mode-map (kbd "C-x i e") 'yas/expand)

  (require 'dropdown-list)
  (setq yas/prompt-functions '(yas/dropdown-prompt
                               yas/ido-prompt
                               yas/completing-prompt))

  (setq yas/buffer-local-condition
        '(or (not (or (string= "font-lock-comment-face"
                               (get-char-property (point) 'face))
                      (string= "font-lock-string-face"
                               (get-char-property (point) 'face))))
             '(require-snippet-condition . force-in-comment)))

  (defun ac-yasnippet-candidate ()
    (let ((table (yas/get-snippet-tables major-mode)))
      (if table
          (let (candidates (list))
            (mapcar (lambda (mode)
                      (maphash (lambda (key value)
                                 (push key candidates))
                               (yas/snippet-table-hash mode)))
                    table)
            (all-completions ac-prefix candidates)))))

  (defface ac-yasnippet-candidate-face
    '((t (:background "sandybrown" :foreground "black")))
    "Face for yasnippet candidate.")

  (defface ac-yasnippet-selection-face
    '((t (:background "coral3" :foreground "white")))
    "Face for the yasnippet selected candidate.")

  (defvar ac-source-yasnippet
    '((candidates . ac-yasnippet-candidate)
      (action . yas/expand)
      (limit . 3)
      (candidate-face . ac-yasnippet-candidate-face)
      (selection-face . ac-yasnippet-selection-face))
    "Source for Yasnippet.")

  (provide 'auto-complete-yasnippet)
  (yas/initialize))

;; auto-complete.el
(when (require 'auto-complete nil t)
  (require 'auto-complete-config)
  (global-auto-complete-mode t)
  (set-face-background 'ac-candidate-face "lightgray")
  (set-face-underline 'ac-candidate-face "darkgray")
  (set-face-background 'ac-selection-face "steelblue")
  (ac-set-trigger-key "TAB")
  (setq ac-auto-start 3)
  (setq ac-dwim t)
  (set-default 'ac-sources '(ac-source-yasnippet
                             ac-source-abbrev
                             ac-source-words-in-buffer)))

;; ruby-mode
(autoload 'ruby-mode "ruby-mode" "Mode for editing ruby source files" t)
(setq auto-mode-alist (cons '("\\.rb$" . ruby-mode) auto-mode-alist))
(setq interpreter-mode-alist (append '(("ruby" . ruby-mode)) interpreter-mode-alist))
(setq ruby-indent-level 2)
(setq ruby-indent-tabs-mode nil)
(autoload 'run-ruby "inf-ruby" "Run an inferior Ruby process")
(autoload 'inf-ruby-keys "inf-ruby" "Set local key defs for inf-ruby in ruby-mode")

;; ruby-electric.el
(require 'ruby-electric)
;; ruby-block.el
(require 'ruby-block)
;; Rinari
(require 'rinari)
(add-hook 'ruby-mode-hook '(lambda ()
                             (inf-ruby-keys)
                             (ruby-block-mode t)
                             (ruby-electric-mode t)
                             (setq ruby-block-highlight-toggle t)))

;; rhtml-mode
(require 'rhtml-mode)
(add-hook 'rhtml-mode-hook (lambda () (rinari-launch)))
(add-to-list 'auto-mode-alist '("¥¥.erb$" . rhtml-mode))

;; yaml-mode
(require  'yaml-mode)
(add-to-list 'auto-mode-alist '("¥¥.yml$" . yaml-mode))

;; scss-mode
(require 'scss-mode)
(setq scss-compile-at-save nil)
(add-to-list 'auto-mode-alist '("¥¥.scss$" . scss-mode))

;; Close all buffers
(require 'cl)
(defun close-all-buffers ()
  (interactive)
  (loop for buffer being the buffers
     do (kill-buffer buffer)))

;; emacsclient
(server-start)