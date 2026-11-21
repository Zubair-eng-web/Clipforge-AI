Set-Location (Split-Path $PSScriptRoot)
$py = ".\.venv\Scripts\python.exe"
function Ram { try { $o = Get-CimInstance Win32_OperatingSystem; [int](100 * ($o.TotalVisibleMemorySize - $o.FreePhysicalMemory) / $o.TotalVisibleMemorySize) } catch { -1 } }
function Ask($q) { $a = Read-Host "$q (y = run, Enter = skip)"; return ($a -eq "y") }
function WaitBackend {
  for ($i = 0; $i -lt 45; $i++) {
    try { Invoke-RestMethod "http://localhost:8000/api/health" -TimeoutSec 3 | Out-Null; return $true } catch { Start-Sleep -Seconds 2 }
  }
  return $false
}
Write-Host "Close Chrome and other heavy apps first. RAM used now: $(Ram)%" -ForegroundColor Cyan

if (Ask "1) Full pytest (backend is stopped first, 5-15 min)") {
  & "$PSScriptRoot\stop-all.ps1"
  Start-Sleep -Seconds 3
  & $py -m pytest -q 2>&1 | Tee-Object -FilePath "logs\pytest_last.txt" | Select-Object -Last 25
}
if (Ask "Start backend + frontend for the next steps?") {
  & "$PSScriptRoot\start-all.ps1"
  if (WaitBackend) { Write-Host "Backend ready. RAM used: $(Ram)%" -ForegroundColor Green } else { Write-Host "Backend did not start in 90 s" -ForegroundColor Red }
}
if (Ask "2) Phase 9 benchmark (Whisper + scenes + highlights, 5-15 min)") {
  & $py scripts\benchmark.py --video-id 1
  Write-Host "Result is in PERFORMANCE_REPORT.md. RAM used: $(Ram)%" -ForegroundColor Green
}
if (Ask "3) 10.4 fixed 1 and 3 minute + custom + duplicates (10-15 min, uses Gemini)") {
  & $py scripts\real_scene_cases.py 1
}
Write-Host "`nDone. Send me: the last lines of pytest, the benchmark table (PERFORMANCE_REPORT.md) and the 4 lines of the 10.4 cases." -ForegroundColor Cyan