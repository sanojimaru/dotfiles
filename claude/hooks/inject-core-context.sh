#!/usr/bin/env bash
set -euo pipefail

CLAUDE_MD="$HOME/.claude/CLAUDE.md"
LOCAL_MD="$HOME/.claude/CLAUDE.local.md"

persona=""
if [ -f "$LOCAL_MD" ]; then
  persona="$(cat "$LOCAL_MD")"
fi

core="$(cat "$CLAUDE_MD" 2>/dev/null || true)"
context="$(printf '%s\n\n%s\n' "$persona" "$core")"

jq -n --arg ctx "$context" \
  '{hookSpecificOutput: {hookEventName: "PostCompact", additionalContext: $ctx}}'
