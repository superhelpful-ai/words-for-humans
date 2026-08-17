#!/bin/sh
# Install the words-for-humans command from PyPI.
#
# The script uses the first Python tool installer it finds on the machine, in
# this order: uv, pipx, pip. uv and pipx put the command in an isolated
# environment and leave your project's dependencies alone. pip installs into
# the user site as a last resort. The script is self-contained. Run it from a
# checkout, send it as a file, or pipe it from a URL.
#
#     sh install.sh
#     curl -LsSf <url>/install.sh | sh
#
# Environment variables:
#
#     WFH_VERSION   exact version to install, for example "0.1.0" (default: latest)
#     WFH_EXTRAS    optional extras, for example "nlp" (default: none)
set -eu

say() { printf '%s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

pkg="words-for-humans"
if [ -n "${WFH_EXTRAS:-}" ]; then
    pkg="${pkg}[${WFH_EXTRAS}]"
fi
if [ -n "${WFH_VERSION:-}" ]; then
    pkg="$pkg==$WFH_VERSION"
fi

if command -v uv >/dev/null 2>&1; then
    say "Installing $pkg with uv"
    uv tool install --force "$pkg"
elif command -v pipx >/dev/null 2>&1; then
    say "Installing $pkg with pipx"
    pipx install --force "$pkg"
elif command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
    say "Installing $pkg with pip into the user site"
    python3 -m pip install --user --upgrade --quiet "$pkg"
else
    fail "no installer found. Install uv first:

    curl -LsSf https://astral.sh/uv/install.sh | sh

then run this script again."
fi

if command -v words-for-humans >/dev/null 2>&1; then
    say ""
    say "Installed: $(command -v words-for-humans)"
else
    say ""
    say "Installed, but words-for-humans is not on PATH yet."
    say "Open a new shell, or add the install directory to PATH:"
    say "    uv:   uv tool update-shell"
    say "    pipx: pipx ensurepath"
    say "    pip:  ~/.local/bin"
fi

say ""
say "Next steps, from your repository root:"
say "    words-for-humans                    see what it finds"
say "    words-for-humans --init             write a starter config"
say "    words-for-humans --write-baseline   accept existing findings; only new prose fails"
