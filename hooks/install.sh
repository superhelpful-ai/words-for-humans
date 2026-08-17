#!/usr/bin/env bash
# Install the pre-commit hook into the repository you are standing in.
#
# An existing hook is moved aside rather than overwritten, because losing
# somebody's hook to a convenience script is not a good trade.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "Not inside a git repository." >&2
    exit 1
fi

hooks_dir="$(git rev-parse --git-path hooks)"
target="$hooks_dir/pre-commit"
mkdir -p "$hooks_dir"

if [[ -e "$target" ]] && ! grep -q "words-for-humans" "$target" 2>/dev/null; then
    backup="$target.before-words-for-humans"
    mv "$target" "$backup"
    echo "Moved the existing hook to $backup"
fi

cp "$script_dir/pre-commit" "$target"
chmod +x "$target"
echo "Installed the pre-commit hook at $target"
echo "Set STE_LINT_SKIP=1 to bypass it for one commit."
