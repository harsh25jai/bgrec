#!/usr/bin/env bash
# Build bgrec test ZIP on GitHub Actions (push to test branch or manual dispatch).
#
# Usage:
#   ./scripts/build-windows-test-from-mac.sh
#   ./scripts/build-windows-test-from-mac.sh --open

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WORKFLOW="build-windows-test.yml"
ARTIFACT_ZIP="bgrec-windows-test"
OUT_DIR="$ROOT/dist"

OPEN_BROWSER=false
for arg in "$@"; do
  case "$arg" in
    --open) OPEN_BROWSER=true ;;
    -h|--help)
      sed -n '2,10p' "$0"
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

BRANCH="$(git branch --show-current 2>/dev/null || echo test)"
if [[ "$BRANCH" != "test" ]]; then
  echo "WARNING: Current branch is '$BRANCH', not 'test'."
  echo "         Push will trigger test workflow only when pushed to origin/test."
  read -r -p "Continue anyway? [y/N] " ans || true
  [[ "${ans:-}" =~ ^[yY] ]] || exit 1
fi

echo "==> Pushing branch ($BRANCH) to origin..."
git push -u origin "$BRANCH" 2>/dev/null || git push origin "$BRANCH"

echo "==> Starting workflow: $WORKFLOW (also runs automatically on push to test)"
if ! gh workflow run "$WORKFLOW" --ref "$BRANCH" 2>/dev/null; then
  echo "    (Manual dispatch may require the workflow on default branch first; waiting for push-triggered run...)"
fi
sleep 4

RUN_ID="$(gh run list --workflow="$WORKFLOW" --branch="$BRANCH" --limit 1 --json databaseId --jq '.[0].databaseId')"
[[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] || die "Could not find workflow run"

echo "==> Run $RUN_ID — waiting for build..."
gh run watch "$RUN_ID" --exit-status

if $OPEN_BROWSER; then
  gh run view "$RUN_ID" --web
fi

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/bgrec-Windows-test.zip"
gh run download "$RUN_ID" --name "$ARTIFACT_ZIP" --dir "$OUT_DIR"

echo ""
echo "==> Test build complete"
echo "    ZIP: $OUT_DIR/bgrec-Windows-test.zip"
if [[ -f "$OUT_DIR/bgrec-Windows-test.zip" ]]; then
  rm -rf "$OUT_DIR/bgrec-Windows-test"
  unzip -q -o "$OUT_DIR/bgrec-Windows-test.zip" -d "$OUT_DIR/bgrec-Windows-test"
  echo "    Folder: $OUT_DIR/bgrec-Windows-test/"
  echo ""
  echo "Copy to Windows PC, unzip, run: install-portable.cmd"
fi
