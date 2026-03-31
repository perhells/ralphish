#!/bin/bash
set -e
set -o pipefail

CLAUDE_JSON="$HOME/.claude.json"
tmp=$(mktemp)
(cat "$CLAUDE_JSON" 2>/dev/null || echo '{}') | jq '.hasCompletedOnboarding = true' >"$tmp" && mv "$tmp" "$CLAUDE_JSON"
