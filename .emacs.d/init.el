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

;;for Mac 
(setq mac-allow-anti-aliasing t)
(setq mac-control-modifier 'control)
(setq mac-option-modifier 'meta)

;; Fonts
(let* ((size 15)
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

;; install-elisp.el
(when (require 'install-elisp nil t)
  (setq install-elisp-repository-directory "~/.emacs.d/elisp"))

;; auto-install.el 
(when (require 'auto-install nil t)
  (setq auto-install-directory "~/.emacs.d/elisp")
  (auto-install-update-emacswiki-package-name t)
  (auto-install-compatibility-setup))

;; anything
(require 'anything)

;; emacsclient
(server-start)