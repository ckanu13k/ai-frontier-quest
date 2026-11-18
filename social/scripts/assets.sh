#!/usr/bin/env bash
# Pull or push the social-assets branch (rendered slides, queue, publish state).
# The branch is kept as a single commit, so images never pile up in git history.
#   social/scripts/assets.sh pull <dir>
#   social/scripts/assets.sh push <dir> "<message>"
set -euo pipefail
cmd=$1; dir=$2
remote="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
if [ "$cmd" = pull ]; then
  if git clone --quiet --depth 1 --branch social-assets "$remote" "$dir" 2>/dev/null; then
    echo "Pulled social-assets."
  else
    echo "No social-assets branch yet; starting fresh."
    mkdir -p "$dir"
  fi
elif [ "$cmd" = push ]; then
  cd "$dir"
  rm -rf .git
  git init --quiet -b social-assets
  git config user.name "aifq-social-bot"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git add -A
  git commit --quiet -m "${3:-update social assets}"
  git push --quiet --force "$remote" social-assets
  echo "Pushed social-assets."
else
  echo "usage: assets.sh pull|push <dir> [message]" >&2; exit 2
fi
