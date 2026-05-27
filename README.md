# bgrec

A **Windows 10/11** command-line utility for **user-consented** microphone recording with **AES-256-GCM encryption** and backup to **your own Google Drive**.

This is not stealth software: startup uses the standard per-user **Run** registry key (visible in Task Manager → Startup), and all behavior is controlled via CLI and config.

## Features

- Continuous microphone recording in **5-minute chunks** (configurable)
- **MP3** output by default (FLAC optional; via pydub + ffmpeg)
- Optional **AES-256-GCM** encryption before upload (off by default)
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
| Python | 3.11+ (3.12+ recommended for builds) |
| ffmpeg | Auto-installed via winget by `install.ps1` / `install-portable.cmd` if missing |
| Google Cloud | OAuth Desktop client + Drive API enabled |

**macOS/Linux:** You can install deps for code editing only (`pip install -r requirements.txt`). The app will not record audio off Windows. Use `requirements-windows.txt` on the target PC (includes PyInstaller).

## Project layout

```
bgrec/
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

Data directory (default): `%LOCALAPPDATA%\bgrec\`  
(Existing installs under `%LOCALAPPDATA%\BackgroundAudioRecorder\` are still used automatically until you migrate data.)

## Quick start — one script on Windows (recommended)

No zip, no repo copy. Push this project to GitHub once, then on any Windows PC paste **one line** into PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force; Invoke-Expression ((New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/YOUR_USER/bgrec/main/install.ps1'))
```

Replace `YOUR_USER/bgrec` with your repo. The script will:

1. Download the app from GitHub  
2. Install Python packages into `%LOCALAPPDATA%\bgrec\`  
3. Add `bgrec` to your user PATH  
4. Install **ffmpeg** via winget if it is not already on PATH  

**First-time setup on Mac** (print your personalized one-liner):

```bash
chmod +x scripts/print-install-oneliner.sh
./scripts/print-install-oneliner.sh your-github-user/bgrec
```

**Or** save only `install.ps1` on a USB/email, open PowerShell on Windows, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install.ps1 -GitHubRepo "your-github-user/bgrec" -InstallPython
```

`-InstallPython` uses `winget` when Python 3.11+ is missing. **ffmpeg** is installed automatically the same way (use `-SkipFfmpeg` to opt out).

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

   `%LOCALAPPDATA%\bgrec\credentials\credentials.json`

5. Authenticate:

```powershell
python -m app.cli.main login-google
# or after pip install:
bgrec login-google
```

### 3. Configure

Edit `%LOCALAPPDATA%\bgrec\config.toml` or use:

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
gh repo create bgrec --private --source=. --push

# Build on Windows cloud runner; download ZIP to dist/
chmod +x scripts/build-windows-from-mac.sh
./scripts/build-windows-from-mac.sh
```

Output:

- `dist/bgrec-Windows.zip` — copy to any Windows PC
- Unzip → run `install-portable.cmd` — starts recording automatically and adds Windows startup (no Python needed)

You can also trigger the build in the browser: **GitHub → Actions → Build Windows EXE → Run workflow**.

### Build on Windows (local)

```cmd
pip install -r requirements-windows.txt
pip install -e .
python scripts\verify_deps.py
python scripts\build_exe.py
scripts\package-windows-release.cmd
```

Note: use `requirements-windows.txt` (not `requirements-windoes.txt`). It includes PyInstaller plus everything in `requirements.txt`.

If PyInstaller fails, open `build\pyinstaller-last.log`. Check deps only: `python scripts\build_exe.py --check-only`.

Alternatives (same output ZIP):

```cmd
scripts\package-windows-release.cmd
bash scripts/package-windows-release.sh
powershell -File scripts\package-windows-release.ps1
```

Output: `dist\bgrec-Windows.zip`

### Install portable EXE on target PC

```cmd
REM After unzipping the release folder:
install-portable.cmd
```

The installer **starts recording in the background** and adds a **Windows startup** entry (runs again after sign-in). `ffmpeg` is installed via winget if missing.

Optional later: `bgrec login-google` (Drive upload). Skip auto-start: `install-portable.cmd -NoAutoStart -SkipStartupRegistry`

## Security notes

- Encryption key: `%LOCALAPPDATA%\bgrec\encryption.key` (user-only ACL best effort).
- When `encryption.enabled = true`, **local** copies stay as `.enc` under `recordings\encrypted\`; **Google Drive** gets normal `.mp3` / `.flac` (decrypted at upload time). Default is encryption off.

### Hearing your recordings

| Where | Encryption off | Encryption on |
|-------|----------------|---------------|
| **This PC** | Plain `.mp3` in `recordings\` | `.enc` in `recordings\encrypted\` (decrypt locally — see developer note below) |
| **Google Drive** | Plain `.mp3` | Plain `.mp3` (play in browser or any app) |

Key file for local `.enc` only: `%LOCALAPPDATA%\bgrec\encryption.key` (Drive files are not encrypted).

### Developers only — decrypt local `.enc` files

The `bgrec` CLI does not expose a `decrypt` command. Use the standalone tools in the repo / release ZIP:

```cmd
decrypt-recording.cmd "%LOCALAPPDATA%\bgrec\recordings\encrypted\rec_20250101_120000.mp3.enc"
```

Or from a dev checkout:

```cmd
python scripts\decrypt_recording.py "path\to\file.mp3.enc"
python scripts\decrypt_recording.py file.mp3.enc -o playback.mp3
```

Requires `encryption.key` on the same machine that recorded the file.
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
| `No module named typer` / `main.py` in traceback | Wrong launcher on PATH. Run `where bgrec` — use `%LOCALAPPDATA%\bgrec\bin\bgrec.exe`. Remove legacy `%LOCALAPPDATA%\bgrec\bgrec.cmd` and re-run `install-portable.cmd`, or rebuild the exe after updating PyInstaller settings. |
| `TOMLDecodeError` at `device = null` (line 7) | Not Google OAuth — invalid TOML. Delete `device = null` from `%LOCALAPPDATA%\bgrec\config.toml` or delete the file and run `bgrec status` to recreate. Newer builds auto-repair this. |
| `NoneType` is not TOML serializable / empty `config.toml` | Old build tried to save `device = null`. Delete `%LOCALAPPDATA%\bgrec\config.toml` and run `bgrec status`, or restore `config.toml.bak`. Rebuild `bgrec.exe` from latest source. |
| Google not signed in | Recording still works; files go to `recordings\` and `cache\pending\`. Run `bgrec login-google` when ready. `bgrec status` shows Google auth state. |
| Device disconnect | Recorder auto-retries every few seconds |

## License

MIT — use responsibly and only with consent of recorded parties and applicable law.