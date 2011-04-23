;; Console settings
;; メニューバー非表示
(menu-bar-mode 0)

;; 対応する括弧を表示
(setq show-paren-delay 0)
(show-paren-mode t)
;; (set-face-background 'show-paren-match-face "yellow")

;; 複数フレームを開かないようにする
(setq ns-pop-up-frames nil)

;; 行番号、列番号
(global-linum-mode)
(column-number-mode t)
(setq default-fill-column 80)

;; ハイライト
(global-hl-line-mode t)

;; ウィンドウサイズ
(setq initial-frame-alist
      (append
       '((width . 160)
         (height . 45))
       initial-frame-alist))

;; wombat
;; (install-elisp "http://www.elektronensturm.de/files/dateien/color-theme-wombat.el")
(require 'color-theme-wombat)
(color-theme-wombat)
