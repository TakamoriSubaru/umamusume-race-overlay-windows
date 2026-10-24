#!/usr/bin/env bash
# Publishes a new version on GitHub as a Release (GitHub builds the zip for you).
# Usage:  ./release.sh 1.4.1
#
# Before you run it, add a "## 1.4.1" section at the top of CHANGELOG.md.
# The text of that section becomes the release notes and the text in the update window.
set -e
cd "$(dirname "$0")"
ROOT="$(git rev-parse --show-toplevel)"
VER="${1:-}"
if ! [[ "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Usage: ./release.sh 1.4.1   (three numbers)"; exit 1
fi
if ! grep -q "^## $VER\$" "$ROOT/CHANGELOG.md"; then
  echo "CHANGELOG.md has no '## $VER' section. Write what changed first, then run this again."; exit 1
fi
if git rev-parse "v$VER" >/dev/null 2>&1; then
  echo "Version $VER already has a tag. Pick a new number."; exit 1
fi
sed -i -E "s/^APP_VERSION = \"[^\"]+\"/APP_VERSION = \"$VER\"/" race_overlay/constants.py
git -C "$ROOT" add -A
if ! git -C "$ROOT" diff --cached --quiet; then
  git -C "$ROOT" commit -m "Version $VER"
fi
git -C "$ROOT" tag "v$VER"
git -C "$ROOT" push origin HEAD
git -C "$ROOT" push origin "v$VER"
echo
echo "Done. GitHub is building the release now (about a minute):"
echo "  https://github.com/TakamoriSubaru/umamusume-race-overlay-windows/releases"
