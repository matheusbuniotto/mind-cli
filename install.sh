#!/usr/bin/env sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found; installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# The uv installer usually writes to ~/.local/bin. Add it for this shell in
# case the user's PATH has not been refreshed yet.
export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv installation finished, but uv is not on PATH." >&2
  echo "Open a new shell, then run: uv tool install mind-cli" >&2
  exit 1
fi

echo "Installing mind-cli with uv..."
uv tool install mind-cli

if ! command -v mind >/dev/null 2>&1; then
  echo "mind installed, but the executable is not on PATH yet." >&2
  echo "Open a new shell, then run: mind init" >&2
  exit 1
fi

mind --version
echo
echo "Next step:"
echo "  mind init"
