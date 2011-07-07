;; mmm-mode
(require 'mmm-mode)
(setq mmm-global-mode 'maybe)
(setq mmm-submode-decoration-level 2)
(setq mmm-font-lock-available-p t)
(invert-face 'mmm-default-submode-face nil)

;; html+js
(mmm-add-classes
 '((mmm-js
    :submode js-mode
    :front "<script[^>]*>[^<]"
    :front-offset -1
    :back "\n?[ \t]*</script>")))

;; html+css
(mmm-add-classes
 '((mmm-css
    :submode css-mode
    :front "<style[^>]*>[^<]"
    :back "\n?[ \t]*</style>")))
