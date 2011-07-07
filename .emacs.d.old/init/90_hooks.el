;; 保存時のhook
(add-hook 'before-save-hook
          '(lambda()
             (delete-trailing-whitespace)))