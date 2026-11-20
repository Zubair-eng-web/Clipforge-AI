$root = Split-Path $PSScriptRoot
$pidFile = Join-Path $root "logs\pids.txt"
if (Test-Path $pidFile) {
  Get-Content $pidFile | Where-Object { $_ } | ForEach-Object { taskkill /PID $_ /T /F 2>$null | Out-Null }
  Remove-Item $pidFile -Force
}
# ports par atke processes
foreach ($port in 8000, 3000) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { taskkill /PID $_.OwningProcess /T /F 2>$null | Out-Null }
}
# is project ke python/node processes (command line se) aur uvicorn workers
$rootEsc = [regex]::Escape($root)
Get-CimInstance Win32_Process |
  Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -and
    (($_.Name -match '^(python|node)(\.exe)?$' -and $_.CommandLine -match $rootEsc) -or
     ($_.Name -match '^python(\.exe)?$' -and $_.CommandLine -match 'uvicorn'))
  } |
  ForEach-Object { taskkill /PID $_.ProcessId /T /F 2>$null | Out-Null }
Write-Host "CLIPFORGE AI stopped." -ForegroundColor Yellow
