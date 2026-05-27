On Windows — paste one line
After your repo is on GitHub (your-user/background-recorder):

Set-ExecutionPolicy -Scope Process Bypass -Force; Invoke-Expression ((New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/YOUR_USER/background-recorder/main/install.ps1'))
With automatic Python + ffmpeg via winget:

Set-ExecutionPolicy -Scope Process Bypass -Force; $s = (New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/YOUR_USER/background-recorder/main/install.ps1'); Invoke-Expression "$s -GitHubRepo 'YOUR_USER/background-recorder' -InstallPython -InstallFfmpeg"
Then open a new terminal:

bgrec login-google
bgrec start --background
On Mac — get your personalized line
./scripts/print-install-oneliner.sh your-github-user/background-recorder
Alternative: copy only install.ps1
Copy that single file to Windows (USB, email, etc.) and run:


.\install.ps1 -GitHubRepo "your-user/background-recorder" -InstallPython -InstallFfmpeg
