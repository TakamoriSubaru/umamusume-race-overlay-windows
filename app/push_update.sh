#!/usr/bin/env bash
# Sends all your changes to GitHub in one command.
# Usage:  ./push_update.sh "short description of what changed"
cd "$(dirname "$0")" || exit 1
MSG="${1:-Update}"

if [ -z "$(git status --porcelain)" ]; then
  echo "Nothing changed, so there is nothing to push."
  exit 0
fi

git add -A
git commit -m "$MSG" || exit 1
if ! git push; then
  echo
  echo "Push failed. Check that you are logged in:  gh auth status"
  echo "and that the repo is connected:             git remote -v"
  exit 1
fi
echo
echo "Done. Latest commits:"
git log --oneline -3
