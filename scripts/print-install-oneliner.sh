#!/usr/bin/env bash
# Print the PowerShell one-liner to install on Windows (after pushing install.ps1 to GitHub).
#
# Usage:
#   ./scripts/print-install-oneliner.sh your-github-user/background-recorder

set -euo pipefail
REPO="${1:-YOUR_GITHUB_USER/background-recorder}"
BRANCH="${2:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}/install.ps1"

cat <<EOF

Paste this into PowerShell on Windows (Run as normal user):

Set-ExecutionPolicy -Scope Process Bypass -Force; \\
  Invoke-Expression ((New-Object Net.WebClient).DownloadString('${RAW}'))

Or with winget helpers for Python/ffmpeg:

Set-ExecutionPolicy -Scope Process Bypass -Force; \\
  \$s = (New-Object Net.WebClient).DownloadString('${RAW}'); \\
  Invoke-Expression "\$s -GitHubRepo '${REPO}' -InstallPython -InstallFfmpeg"

Edit install.ps1 default \$GitHubRepo, push to GitHub, then use the one-liner above.

EOF
