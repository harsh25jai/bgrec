#!/usr/bin/env bash
# Build bgrec.exe on GitHub Actions (Windows runner) and download the portable ZIP.
# PyInstaller cannot cross-compile Windows binaries on macOS.
#
# Prerequisites:
#   brew install gh
#   gh auth login
#   git remote pointing to GitHub (or create one)
#
# Usage:
#   ./scripts/build-windows-from-mac.sh
#   ./scripts/build-windows-from-mac.sh --open   # open Actions page in browser

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WORKFLOW="build-windows.yml"
ARTIFACT_ZIP="bgrec-windows-release"
OUT_DIR="$ROOT/dist"

OPEN_BROWSER=false
for arg in "$@"; do
  case "$arg" in
    --open) OPEN_BROWSER=true ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "Install GitHub CLI: brew install gh && gh auth login"
command -v git >/dev/null 2>&1 || die "git is required"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "Not a git repository. Run: git init && gh repo create"
fi

if ! gh auth status >/dev/null 2>&1; then
  die "Not logged in to GitHub. Run: gh auth login"
fi

REMOTE="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REMOTE" ]]; then
  die "No git remote 'origin'. Add GitHub remote: git remote add origin <url>"
fi

BRANCH="$(git branch --show-current 2>/dev/null || echo main)"
echo "==> Pushing current branch ($BRANCH) so Actions uses latest code..."
git push -u origin "$BRANCH" 2>/dev/null || git push origin "$BRANCH"

echo "==> Starting workflow: $WORKFLOW"
gh workflow run "$WORKFLOW" --ref "$BRANCH"
sleep 3

RUN_ID="$(gh run list --workflow="$WORKFLOW" --limit 1 --json databaseId --jq '.[0].databaseId')"
[[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] || die "Could not find workflow run"

echo "==> Run $RUN_ID — waiting for build (typically 3–6 minutes)..."

gh run watch "$RUN_ID" --exit-status

if $OPEN_BROWSER; then
  gh run view "$RUN_ID" --web
fi

mkdir -p "$OUT_DIR"
rm -rf "$OUT_DIR"/bgrec-Windows "$OUT_DIR"/bgrec-Windows.zip
gh run download "$RUN_ID" --name "$ARTIFACT_ZIP" --dir "$OUT_DIR"

echo ""
echo "==> Build complete"
echo "    ZIP: $OUT_DIR/bgrec-Windows.zip"
if [[ -f "$OUT_DIR/bgrec-Windows.zip" ]]; then
  unzip -q -o "$OUT_DIR/bgrec-Windows.zip" -d "$OUT_DIR/bgrec-Windows"
  echo "    Folder: $OUT_DIR/bgrec-Windows/"
  echo ""
  echo "Copy bgrec-Windows.zip to the target PC, unzip, and run:"
  echo "  .\\install-portable.ps1"
else
  echo "    (Downloaded artifact contents are in $OUT_DIR)"
fi
