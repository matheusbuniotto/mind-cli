#!/usr/bin/env bash
# mind session check — no LLM. Installed by: mind init / mind install
# Usage: mind-check.sh [claude|cursor|codex|auto]

set -euo pipefail

if ! command -v mind >/dev/null 2>&1; then
  exit 0
fi

AGENT="${1:-auto}"
# Codex/Claude pass cwd on stdin when piped
if [ ! -t 0 ]; then
  exec mind check --hook "$AGENT" --quiet
fi
exec mind check --hook "$AGENT" --quiet
