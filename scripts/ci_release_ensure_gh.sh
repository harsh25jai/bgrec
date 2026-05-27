#!/usr/bin/env bash
# Create draft GitHub release if missing (tag must exist on remote).

set -euo pipefail

: "${TAG:?TAG required}"
: "${REPO:?REPO required}"

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "GitHub release ${TAG} already exists."
  exit 0
fi

echo "Creating draft GitHub release ${TAG}."
gh release create "$TAG" --draft --verify-tag --repo "$REPO" \
  --title "$TAG" \
  --generate-notes
