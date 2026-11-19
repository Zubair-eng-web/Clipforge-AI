$pidFile = Join-Path (Split-Path $PSScriptRoot) "logs\pids.txt"
if (Test-Path $pidFile) {
  Get-Content $pidFile | Where-Object { $_ } | ForEach-Object { taskkill /PID $_ /T /F 2>$null | Out-Null }
  Remove-Item $pidFile -Force
}
# Backup: agar koi process ports par atka reh gaya ho
foreach ($port in 8000, 3000) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { taskkill /PID $_.OwningProcess /T /F 2>$null | Out-Null }
}
Write-Host "CLIPFORGE AI stopped." -ForegroundColor Yellow