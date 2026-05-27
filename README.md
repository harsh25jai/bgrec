# Background Audio Recorder

A **Windows 10/11** command-line utility for **user-consented** microphone recording with **AES-256-GCM encryption** and backup to **your own Google Drive**.

This is not stealth software: startup uses the standard per-user **Run** registry key (visible in Task Manager → Startup), and all behavior is controlled via CLI and config.

## Features

- Continuous microphone recording in **5-minute chunks** (configurable)
- **FLAC** or **MP3** output (via pydub + ffmpeg)
- **AES-256-GCM** encryption before upload
- **Google Drive** upload with OAuth desktop flow
- Retry / resume pending uploads after reboot
- **HKCU Run** startup integration (optional)
- Rotating structured logs (loguru)
- Local retention policy
- Single-file **PyInstaller** build (`bgrec.exe`)

## Requirements

| Component | Version |
|-----------|---------|
| OS | Windows 10/11 (runtime) |
| Python | 3.12+ |
| ffmpeg | Auto-installed via winget by `install.ps1` / `install-portable.cmd` if missing |
| Google Cloud | OAuth Desktop client + Drive API enabled |

**macOS/Linux:** You can install deps for code editing only (`pip install -r requirements.txt`). The app will not record audio off Windows. Use `requirements-windows.txt` on the target PC (includes PyInstaller).

## Project layout

```
background-recorder/
├── app/
│   ├── recorder/       # Microphone capture & conversion
│   ├── uploader/       # Google Drive client & queue
│   ├── crypto/         # AES-256-GCM
│   ├── scheduler/      # Service coordinator
│   ├── retention/      # Local cleanup
│   ├── startup/        # Windows Run registry
│   ├── service/        # Daemon, state, watchdog
│   ├── config/         # TOML settings
│   ├── logging/        # loguru setup
│   └── cli/            # Typer commands
├── config/config.toml.example
├── scripts/build_exe.py
├── install.ps1
├── uninstall.ps1
└── requirements.txt
```

Data directory (default): `%LOCALAPPDATA%\BackgroundAudioRecorder\`

## Quick start — one script on Windows (recommended)

No zip, no repo copy. Push this project to GitHub once, then on any Windows PC paste **one line** into PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force; Invoke-Expression ((New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/YOUR_USER/background-recorder/main/install.ps1'))
```

Replace `YOUR_USER/background-recorder` with your repo. The script will:

1. Download the app from GitHub  
2. Install Python packages into `%LOCALAPPDATA%\BackgroundAudioRecorder\`  
3. Add `bgrec` to your user PATH  
4. Install **ffmpeg** via winget if it is not already on PATH  

**First-time setup on Mac** (print your personalized one-liner):

```bash
chmod +x scripts/print-install-oneliner.sh
./scripts/print-install-oneliner.sh your-github-user/background-recorder
```

**Or** save only `install.ps1` on a USB/email, open PowerShell on Windows, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install.ps1 -GitHubRepo "your-github-user/background-recorder" -InstallPython
```

`-InstallPython` uses `winget` when Python 3.12+ is missing. **ffmpeg** is installed automatically the same way (use `-SkipFfmpeg` to opt out).

### Dev install (from a local clone)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

### 2. Google Drive setup

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project → enable **Google Drive API**.
3. Create **OAuth 2.0 Client ID** → type **Desktop app**.
4. Download JSON and save as:

   `%LOCALAPPDATA%\BackgroundAudioRecorder\credentials\credentials.json`

5. Authenticate:

```powershell
python -m app.cli.main login-google
# or after pip install:
bgrec login-google
```

### 3. Configure

Edit `%LOCALAPPDATA%\BackgroundAudioRecorder\config.toml` or use:

```powershell
bgrec config
bgrec config --key recording.device --value "Microphone"
bgrec list-devices
```

### 4. Run

```powershell
# Background daemon
bgrec start --background

# Status
bgrec status

# Upload any pending files manually
bgrec upload-pending

# Stop
bgrec stop
```

### 5. Optional: start on login

```powershell
bgrec install-startup
```

Removes with:

```powershell
bgrec uninstall-startup
```

## CLI reference

| Command | Description |
|---------|-------------|
| `start` | Start recording (`--background` for detached) |
| `stop` | Stop background service |
| `status` | Show PID, chunks, pending uploads |
| `login-google` | OAuth flow for Drive |
| `upload-pending` | Upload queued encrypted files |
| `config` | Show/update TOML config |
| `list-recordings` | List local audio files |
| `list-devices` | List microphone devices |
| `delete-local-cache` | Clear pending upload cache |
| `install-startup` | Add HKCU Run entry |
| `uninstall-startup` | Remove Run entry |

## Build Windows EXE from macOS

PyInstaller **cannot** produce a Windows `.exe` on macOS. Use **GitHub Actions** (free Windows builder):

```bash
# One-time setup
brew install gh
gh auth login
git init
gh repo create background-recorder --private --source=. --push

# Build on Windows cloud runner; download ZIP to dist/
chmod +x scripts/build-windows-from-mac.sh
./scripts/build-windows-from-mac.sh
```

Output:

- `dist/BackgroundAudioRecorder-Windows.zip` — copy to any Windows PC
- Unzip → run `install-portable.ps1` (no Python needed on target PC)

You can also trigger the build in the browser: **GitHub → Actions → Build Windows EXE → Run workflow**.

### Build on Windows (local)

```cmd
pip install -r requirements-windows.txt
python scripts\build_exe.py
scripts\package-windows-release.cmd
```

Alternatives (same output ZIP):

```cmd
scripts\package-windows-release.cmd
bash scripts/package-windows-release.sh
powershell -File scripts\package-windows-release.ps1
```

Output: `dist\BackgroundAudioRecorder-Windows.zip`

### Install portable EXE on target PC

```cmd
REM After unzipping the release folder:
install-portable.cmd
```

(`ffmpeg` is installed automatically via winget if missing.)

Or PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-portable.ps1

# New terminal:
bgrec login-google
bgrec start --background
```

## Security notes

- Encryption key: `%LOCALAPPDATA%\BackgroundAudioRecorder\encryption.key` (user-only ACL best effort).
- When `encryption.enabled = true`, only `.enc` files are queued for upload.
- No privilege escalation, no hidden persistence — startup is a normal user Run key.
- Validate paths stay under configured data directories.

## Uninstall

```powershell
.\uninstall.ps1
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No audio | Check mic privacy: Settings → Privacy → Microphone |
| FLAC/MP3 fails / pydub ffmpeg warning | Re-run `install-portable.cmd` or `install.ps1` (auto-installs ffmpeg). Manual: `winget install -e Gyan.FFmpeg`, then open a new terminal. Without ffmpeg, recordings stay WAV. |
| Upload fails | Run `bgrec login-google`; check `logs\upload.log` |
| `No module named typer` / `main.py` in traceback | Wrong launcher on PATH. Run `where bgrec` — use `%LOCALAPPDATA%\BackgroundAudioRecorder\bin\bgrec.exe`. Remove legacy `%LOCALAPPDATA%\BackgroundAudioRecorder\bgrec.cmd` and re-run `install-portable.cmd`, or rebuild the exe after updating PyInstaller settings. |
| Device disconnect | Recorder auto-retries every few seconds |

## License

MIT — use responsibly and only with consent of recorded parties and applicable law.