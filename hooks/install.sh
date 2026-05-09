#!/usr/bin/env bash
# install.sh — wire pre-commit + pre-push into .git/hooks of the current clone.
# Idempotent. Run once per clone.

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

mkdir -p .git/hooks
ln -sf ../../hooks/pre-commit .git/hooks/pre-commit
ln -sf ../../hooks/pre-push   .git/hooks/pre-push
chmod +x hooks/pre-commit hooks/pre-push

echo "✓ Linked .git/hooks/pre-commit → hooks/pre-commit"
echo "✓ Linked .git/hooks/pre-push   → hooks/pre-push"
