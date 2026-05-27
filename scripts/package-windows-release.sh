#!/usr/bin/env bash
# Package bgrec.exe + portable installer into a ZIP (Git Bash / MSYS on Windows).
# Run after: python scripts/build_exe.py
#
# Usage:
#   ./scripts/package-windows-release.sh
#   bash scripts/package-windows-release.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
EXE="$DIST/bgrec.exe"
RELEASE_DIR="$DIST/BackgroundAudioRecorder-Windows"
ZIP="$DIST/BackgroundAudioRecorder-Windows.zip"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$EXE" ]] || die "Missing $EXE — run: python scripts/build_exe.py"

rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

cp "$EXE" "$RELEASE_DIR/"
cp "$ROOT/install-portable.ps1" "$RELEASE_DIR/"
cp "$ROOT/install-portable.cmd" "$RELEASE_DIR/"
cp "$ROOT/scripts/windows-ensure-ffmpeg.ps1" "$RELEASE_DIR/"
cp "$ROOT/uninstall.ps1" "$RELEASE_DIR/"
cp "$ROOT/config/config.toml.example" "$RELEASE_DIR/"
cp "$ROOT/README.md" "$RELEASE_DIR/"
cp "$ROOT/scripts/decrypt_recording.py" "$RELEASE_DIR/"
cp "$ROOT/decrypt-recording.cmd" "$RELEASE_DIR/"

cat > "$RELEASE_DIR/INSTALL.txt" <<'EOF'
Background Audio Recorder — portable install
============================================

1. Unzip this folder anywhere (e.g. Desktop\BackgroundAudioRecorder).
2. Open Command Prompt, Git Bash, or PowerShell here and run:

   ./install-portable.cmd
   OR
   ./install-portable.ps1   (PowerShell: Set-ExecutionPolicy -Scope Process Bypass)

3. Place Google OAuth credentials.json in:
   %LOCALAPPDATA%\BackgroundAudioRecorder\credentials\credentials.json

4. Open a NEW terminal (PATH refresh) and run:

   bgrec login-google
   bgrec start --background

ffmpeg is installed automatically by install-portable.cmd (via winget) if missing.
EOF

rm -f "$ZIP"
(
  cd "$DIST"
  if command -v zip >/dev/null 2>&1; then
    zip -r "BackgroundAudioRecorder-Windows.zip" "BackgroundAudioRecorder-Windows"
  else
    tar -caf "BackgroundAudioRecorder-Windows.zip" "BackgroundAudioRecorder-Windows"
  fi
)

echo ""
echo "Created: $ZIP"
