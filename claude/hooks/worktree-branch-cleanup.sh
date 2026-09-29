#!/bin/bash
# WorktreeRemove hook: debug pass — logs raw stdin JSON for schema inspection.
# Not yet wired to delete branches; see helix session that created this file.
set -u
LOG="$HOME/.claude/hooks/worktree-branch-cleanup.log"
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  cat
  echo
} >> "$LOG"
exit 0
