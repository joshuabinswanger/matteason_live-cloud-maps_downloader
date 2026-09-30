# Entry point for the "CloudMaps Weekly Archive" Windows scheduled task.
# Runs archive_backlog.py, which archives every *finished* ISO week still held
# as per-run maps-* releases and then deletes them. Safe to run late or twice:
# weeks are labelled by capture time and already-archived weeks are skipped.
$repo   = Split-Path -Parent $PSScriptRoot
$logDir = 'D:\SynoDrive\2603_CloudMaps\_backlog_staging\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("weekly_{0:yyyyMMdd_HHmm}.log" -f (Get-Date))

Set-Location $repo
# cmd redirect keeps python's stderr as plain text (PowerShell 5.1 would wrap it in ErrorRecords)
cmd /c "C:\Python314\python.exe -u scripts\archive_backlog.py > `"$log`" 2>&1"
exit $LASTEXITCODE
