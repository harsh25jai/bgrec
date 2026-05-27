#!/usr/bin/env bash
# Trigger a production release on GitHub Actions (Windows build + GitHub Release + OTA manifest).
#
# Normal flow: bump version in pyproject.toml and push to main — CI runs automatically.
# This script pushes main and watches the workflow (or force-dispatches a rebuild).
#
# Usage:
#   ./scripts/build-windows-from-mac.sh
#   ./scripts/build-windows-from-mac.sh --force   # re-release current pyproject version
#   ./scripts/build-windows-from-mac.sh --open

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WORKFLOW="build-windows.yml"
OUT_DIR="$ROOT/dist"

OPEN_BROWSER=false
FORCE=false
for arg in "$@"; do
  case "$arg" in
    --open) OPEN_BROWSER=true ;;
    --force) FORCE=true ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "Install GitHub CLI: brew install gh && gh auth login"
command -v git >/dev/null 2>&1 || die "git is required"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "Not a git repository."
fi

if ! gh auth status >/dev/null 2>&1; then
  die "Not logged in to GitHub. Run: gh auth login"
fi

VERSION="$(python3 scripts/read_version.py 2>/dev/null || true)"
BRANCH="$(git branch --show-current 2>/dev/null || echo main)"

echo "==> Project version (pyproject.toml): ${VERSION:-unknown}"
echo "==> Current branch: $BRANCH"

if [[ "$BRANCH" != "main" ]]; then
  echo "WARNING: Production releases are triggered by pushes to **main** with a pyproject.toml version bump."
  echo "         Merge to main and push, or: git checkout main"
fi

echo "==> Pushing to origin/main..."
git push -u origin main 2>/dev/null || git push origin main || true

if $FORCE; then
  echo "==> Force-dispatching workflow on main..."
  gh workflow run "$WORKFLOW" --ref main -f "force_release=true"
else
  echo "==> If you bumped version in pyproject.toml, CI should already be running."
  echo "    To rebuild the same version: $0 --force"
  LATEST="$(gh run list --workflow="$WORKFLOW" --branch=main --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)"
  if [[ -z "$LATEST" || "$LATEST" == "null" ]]; then
    echo "==> No recent run found — dispatching workflow on main..."
    gh workflow run "$WORKFLOW" --ref main
  fi
fi

sleep 4
RUN_ID="$(gh run list --workflow="$WORKFLOW" --branch=main --limit 1 --json databaseId --jq '.[0].databaseId')"
[[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] || die "Could not find workflow run"

echo "==> Run $RUN_ID — waiting (build + release, typically 5–8 minutes)..."
gh run watch "$RUN_ID" --exit-status

if $OPEN_BROWSER; then
  gh run view "$RUN_ID" --web
fi

echo ""
echo "==> Done. GitHub Release v${VERSION} should include bgrec-Windows.zip and latest.json for OTA."
echo "    Clients with auto_apply will update on next start or within ~6 hours."
