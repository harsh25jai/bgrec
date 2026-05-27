#!/usr/bin/env bash
# Decide whether to run release (writes should_plan + logs reason).
# Env: TAG, VERSION, REPO, FORCE, GITHUB_EVENT_NAME, GITHUB_SHA, GITHUB_EVENT_BEFORE

set -euo pipefail

SHOULD=false
REASON=""

git fetch origin --tags --force

has_remote_tag() {
  git rev-parse "$TAG" >/dev/null 2>&1
}

tag_at_head() {
  has_remote_tag && [[ "$(git rev-parse "$TAG^{}")" == "$GITHUB_SHA" ]]
}

release_has_assets() {
  if ! command -v gh >/dev/null 2>&1; then
    return 1
  fi
  if ! gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
    return 1
  fi
  local count
  count="$(gh release view "$TAG" --repo "$REPO" --json assets -q '.assets | length')"
  [[ "${count:-0}" -gt 0 ]]
}

if [[ "${FORCE:-false}" == "true" ]]; then
  SHOULD=true
  REASON="force_release"
elif [[ "${GITHUB_EVENT_NAME:-}" == "workflow_dispatch" ]]; then
  SHOULD=true
  REASON="workflow_dispatch"
else
  BEFORE="$(git show "${GITHUB_EVENT_BEFORE}:pyproject.toml" 2>/dev/null || true)"
  OLD="$(echo "$BEFORE" | grep -E '^\s*version\s*=' | head -1 | sed -E 's/.*"([^"]+)".*/\1/' || true)"
  if [[ -z "$OLD" ]]; then
    SHOULD=true
    REASON="no parent version (first release)"
  elif [[ "$OLD" != "$VERSION" ]]; then
    SHOULD=true
    REASON="version bump ${OLD} -> ${VERSION}"
  elif ! has_remote_tag; then
    SHOULD=true
    REASON="tag ${TAG} does not exist yet (publish ${VERSION})"
  elif tag_at_head && ! release_has_assets; then
    SHOULD=true
    REASON="tag ${TAG} at this commit but release assets missing (retry)"
  elif tag_at_head && release_has_assets; then
    REASON="already published ${TAG} at this commit"
  elif has_remote_tag; then
    REASON="version unchanged (${VERSION}); tag ${TAG} on another commit — bump pyproject.toml version"
  else
    SHOULD=true
    REASON="publish ${VERSION}"
  fi
fi

if [[ "$SHOULD" == "true" ]]; then
  echo "Will release: ${REASON}"
else
  echo "Skip: ${REASON}"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "should_plan=${SHOULD}" >> "$GITHUB_OUTPUT"
else
  echo "should_plan=${SHOULD}"
fi
