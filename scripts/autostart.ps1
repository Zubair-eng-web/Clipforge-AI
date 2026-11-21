param([switch]$NoDelay)
$root = Split-Path $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
$log = Join-Path $root "logs\autostart.log"
function Log($m) { "$(Get-Date -Format 's')  $m" | Add-Content -Path $log -Encoding UTF8 }
function Up($url) { try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true } catch { return $false } }

Log "autostart begin (NoDelay=$NoDelay)"
if (-not $NoDelay) { Start-Sleep -Seconds 15 }   # login ke baad Windows ko settle hone do

$backendUp  = Up "http://localhost:8000/api/health"
$frontendUp = Up "http://localhost:3000"
if ($backendUp -and $frontendUp) {
  Log "servers already running, only opening Edge"
} else {
  $ids = @()
  if (-not $backendUp) {
    $b = Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList @("-ExecutionPolicy","Bypass","-File","`"$PSScriptRoot\start-backend.ps1`"")
    $ids += $b.Id; Log "backend started pid $($b.Id)"
  }
  if (-not $frontendUp) {
    $f = Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList @("-ExecutionPolicy","Bypass","-File","`"$PSScriptRoot\start-frontend.ps1`"")
    $ids += $f.Id; Log "frontend started pid $($f.Id)"
  }
  ($ids -join "`n") | Set-Content (Join-Path $root "logs\pids.txt")
}

$ok = $false
for ($i = 0; $i -lt 90; $i++) {          # max 3 minute
  if ((Up "http://localhost:8000/api/health") -and (Up "http://localhost:3000")) { $ok = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $ok) { Log "TIMEOUT: servers not ready in 3 minutes (see logs folder)" }

try { Start-Process "msedge.exe" -ArgumentList "http://localhost:3000"; Log "Edge opened" }
catch {
  try { Start-Process "microsoft-edge:http://localhost:3000"; Log "Edge opened (protocol)" }
  catch { Log "Edge could not be opened: $($_.Exception.Message)" }
}
Log "autostart end (ready=$ok)"