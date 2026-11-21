#!/usr/bin/env bash
# 実行: bash tests/agents-md-draft.sh
# 評価の下書きは、AGENTS.md の Issue の進め方の節と同じ文面にする。評価が本番の文面を測るようにするため。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRAFT="$ROOT/agents/skills/issue-planning/evals/agents-md-draft.md"
HEADING="$(head -n 1 "$DRAFT")"
section="$(awk -v h="$HEADING" '$0 == h { f = 1; print; next } f && /^#{1,3} / { exit } f' "$ROOT/agents/AGENTS.md")"
if [ "$section" != "$(cat "$DRAFT")" ]; then
  echo "FAIL agents-md-draft.md が agents/AGENTS.md の「${HEADING#\#\#\# }」の節と違う。節を写し直す" >&2
  diff <(printf '%s\n' "$section") "$DRAFT" >&2 || true
  exit 1
fi
echo "ok   評価の下書きが AGENTS.md の節と同じ"
