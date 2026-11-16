#!/bin/bash
# PreToolUse (AskUserQuestion) フック: 複数の質問や preview 付きの選択肢は、判断に要る背景と中身を本文で読めるように止める。
set -u
command -v jq >/dev/null || { echo "jq が無いので block-heavy-ask-user-question.sh が効いていない" >&2; exit 1; }
if jq -e '.tool_input.questions | length >= 2 or any(.[] | .options[]?; has("preview"))' >/dev/null; then
  cat >&2 <<'EOF'
AskUserQuestion は推奨しません。質問は、基本的に返事の本文で、背景・選択肢ごとの中身・選んだときに起きること・おすすめとその理由を書いてから聞いてください。
AskUserQuestion を使ってよいのは、背景の説明が無くても答えられる軽い確認を、1 回 1 問で聞くときだけです。
EOF
  exit 2
fi
exit 0
