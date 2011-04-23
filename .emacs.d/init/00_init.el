;; server
(server-start)

;; PATH
;; http://sakito.jp/emacs/emacsshell.html#path
;; (dolist (dir (list
;;               "/usr/X11/bin"
;;               "/usr/local/bin"
;;               "/sbin"
;;               "/usr/sbin"
;;               "/bin"
;;               "/usr/bin"
;;               "/usr/local/mysql/bin"
;;               "/Developer/Tools"
;;               "/usr/local/sbin"
;;               "/usr/local/bin"
;;               "/opt/local/sbin"
;;               "/opt/local/bin"
;;               (expand-file-name "~/perl5/perlbrew/perls/current/bin")
;;               (expand-file-name "~/bin")
;;               ))
  ;; PATH と exec-path に同じ物を追加します
  ;; (when ;; (and
  ;;     (file-exists-p dir) ;; (not (member dir exec-path)))
  ;;   (setenv "PATH" (concat dir ":" (getenv "PATH")))
  ;;   (setq exec-path (append (list dir) exec-path))))

;; mail address
(setq user-mail-address "sanojimaru@gmail.com")

;; meta key
;; (setq ns-command-modifier (quote meta))
;; (setq ns-alternate-modifier (quote super))

;; バックアップファイルを残さない
(setq make-backup-files nil)

;; 自動保存しない
(setq auto-save-default nil)

;; ベルを鳴らさない
(setq ring-bell-function 'ignore)

;; 1行ずつスクロール
(setq scroll-step 1)

;; 折り返さない
(setq truncate-lines t)
(setq truncate-partial-width-windows t)

;; インデント設定
(setq-default indent-tabs-mode nil)
(setq-default c-basic-offset 4)
(setq-default tab-width 4)
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

;; スタートページ非表示
(setq inhibit-startup-message t)

;; タイムローケールを英語に
(setq system-time-locale "C")

;; windowの移動をS-矢印に
(windmove-default-keybindings)

;; input methodをMacOSXにする
(setq default-input-method "MacOSX")