# bgrec — install one-liners (notes)

After your repo is on GitHub (`your-user/bgrec`):

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force; Invoke-Expression ((New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/YOUR_USER/bgrec/main/install.ps1'))
```

With automatic Python install if missing:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force; $s = (New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/YOUR_USER/bgrec/main/install.ps1'); Invoke-Expression "$s -GitHubRepo 'YOUR_USER/bgrec' -InstallPython"
```

```cmd
bgrec login-google
bgrec start --background
```

```bash
./scripts/print-install-oneliner.sh your-github-user/bgrec
```

```powershell
.\install.ps1 -GitHubRepo "your-user/bgrec" -InstallPython
```
