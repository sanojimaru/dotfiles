;; 現在の日付を挿入
(defun current-date-string () (interactive) "現在の日付を挿入する" (insert (format-time-string "%Y-%m-%d")))

;; すべてのバッファをkill
(defun kill-all-buffers ()
  (interactive)
  (loop for buffer being the buffers
        do (kill-buffer buffer)))

;; カーソル位置から行頭まで削除する
(defun backward-kill-line (arg)
  "Kill chars backward until encountering the end of a line."
  (interactive "p")
  (kill-line 0))
(define-key global-map (kbd "M-k") 'backward-kill-line)