#!/usr/bin/env sh
# Install project git hooks (pre-commit + commit-msg).

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$ROOT/.githooks"

chmod +x "$HOOKS_DIR/pre-commit" "$HOOKS_DIR/commit-msg"
git -C "$ROOT" config core.hooksPath .githooks

echo "Installed git hooks from .githooks (core.hooksPath=.githooks)"
