#!/usr/bin/env bash
# Create/push annotated tag at GITHUB_SHA if missing. Writes did_push to GITHUB_OUTPUT.

set -euo pipefail

: "${TAG:?TAG required}"
: "${VERSION:?VERSION required}"
: "${GITHUB_SHA:?GITHUB_SHA required}"

git fetch origin --tags --force

if git rev-parse "$TAG" >/dev/null 2>&1; then
  EXISTING="$(git rev-parse "$TAG^{}")"
  if [[ "$EXISTING" != "$GITHUB_SHA" ]]; then
    echo "::error::Tag ${TAG} points at ${EXISTING}; this commit is ${GITHUB_SHA}. Bump version in pyproject.toml or delete tag ${TAG} if safe."
    exit 1
  fi
  echo "Remote tag ${TAG} already at this commit."
  echo "did_push=false" >> "${GITHUB_OUTPUT}"
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git tag -a "${TAG}" -m "Release ${VERSION}" "${GITHUB_SHA}"
git push origin "refs/tags/${TAG}"
echo "Pushed new tag ${TAG}."
echo "did_push=true" >> "${GITHUB_OUTPUT}"
