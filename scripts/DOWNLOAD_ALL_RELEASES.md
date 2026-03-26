# Download All Past Releases

Instructions for downloading all GitHub release assets locally using the GitHub CLI.

## Prerequisites

Install the GitHub CLI:
```powershell
winget install GitHub.cli
```

Then restart your terminal and authenticate:
```bash
gh auth login
```
Choose: **GitHub.com → HTTPS → Login with a web browser**

## Download All Releases

Run this in **PowerShell** from any directory:

```powershell
gh release list --repo joshuabinswanger/matteason_live-cloud-maps_downloader --limit 1000 --json tagName --jq '.[].tagName' | ForEach-Object { gh release download $_ --repo joshuabinswanger/matteason_live-cloud-maps_downloader --pattern "*" --dir ./downloads }
```

Assets will be saved into a `downloads` folder in your current directory.

> Note: There are many releases (every 3 hours), so this may take a while and use significant disk space.
