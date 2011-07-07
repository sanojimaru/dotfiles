;; ruby-mode
(autoload 'ruby-mode "ruby-mode")
(add-to-list 'auto-mode-alist '("\\.rb$" . ruby-mode))

;; ruby-electric
;; (install-elisp "http://shylock.uw.hu/Emacs/ruby-electric.el")
(autoload 'ruby-electric-mode "ruby-electric-mode")

;; inf-ruby
;; (install-elisp "https://github.com/nonsequitur/inf-ruby/raw/master/inf-ruby.el")
(autoload 'run-ruby "inf-ruby" "Run an inferior Ruby process")
(autoload 'inf-ruby-keys "inf-ruby" "Set local key defs for inf-ruby in ruby-mode")

;; insert magic comment if needed .rb
(defun ruby-insert-magic-comment-if-needed ()
  ())

 (add-hook 'before-save-hook 'ruby-insert-magic-comment-if-needed)

;; ruby mode hook
(add-hook 'ruby-mode-hook
          '(lambda()
             (setq ruby-indent-level 2
                   tab-width 2
                   c-basic-offset 2
                   c-hanging-comment-starter-p nil
                   c-hanging-comment-ender-p nil)
             (inf-ruby-keys)
             (ruby-electric-mode t)))



;; haml-mode
;; (auto-install-from-url "https://github.com/nex3/haml-mode/raw/master/haml-mode.el")
(autoload 'haml-mode "haml-mode" "editing for haml source" t)
(add-to-list 'auto-mode-alist '("\\.haml$" . haml-mode))

;; scss-mode
;; (auto-install-from-url "https://github.com/antonj/scss-mode/raw/master/scss-mode.el")
(autoload 'scss-mode "scss-mode" "editing for scss source" t)
(add-to-list 'auto-mode-alist '("\\.scss$" . scss-mode))
(add-hook 'scss-mode-hook
          '(lambda()
             (setq scss-compile-at-save nil)))

;; sass-mode
;; (auto-install-from-url "https://github.com/nex3/sass-mode/raw/master/sass-mode.el")
(autoload 'sass-mode "sass-mode" "editing for sass source" t)
(add-to-list 'auto-mode-alist '("\\.sass$" . sass-mode))